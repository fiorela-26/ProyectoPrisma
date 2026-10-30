-- 002: corrige políticas RLS y el trigger de perfiles.
-- Pegar completo en Supabase -> SQL Editor -> Run. Es idempotente (se puede volver a ejecutar).
-- El cliente de servicio (backend y jobs) salta RLS por diseño, así que estas políticas
-- solo describen lo que puede hacer un usuario autenticado desde su propia sesión.

-- ---------------------------------------------------------------
-- Funciones auxiliares (security definer evita recursión en RLS)
-- ---------------------------------------------------------------
create or replace function public.mi_rol()
returns text language sql stable security definer set search_path = public as $$
  select rol from perfiles where id = auth.uid()
$$;

create or replace function public.es_docente_de(p_curso uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from cursos where id = p_curso and docente_id = auth.uid())
$$;

create or replace function public.esta_inscrito(p_curso uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from inscripciones_curso where curso_id = p_curso and estudiante_id = auth.uid())
$$;

create or replace function public.curso_de_sesion(p_sesion uuid)
returns uuid language sql stable security definer set search_path = public as $$
  select curso_id from sesiones_material where id = p_sesion
$$;

create or replace function public.sesion_publicada(p_sesion uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from sesiones_material where id = p_sesion and estado = 'publicado')
$$;

-- ---------------------------------------------------------------
-- Trigger: crea el perfil al registrarse (nombre y rol vienen en metadata)
-- ---------------------------------------------------------------
create or replace function public.create_profile_if_not_exists()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_rol text := coalesce(new.raw_user_meta_data->>'rol', 'estudiante');
begin
  if v_rol not in ('docente', 'estudiante') then
    v_rol := 'estudiante';
  end if;
  insert into public.perfiles (id, nombre, rol)
  values (new.id, coalesce(new.raw_user_meta_data->>'nombre', new.email), v_rol)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.create_profile_if_not_exists();

-- ---------------------------------------------------------------
-- perfiles
-- ---------------------------------------------------------------
drop policy if exists perfiles_user_self on perfiles;
drop policy if exists perfiles_service_role on perfiles;
create policy perfiles_select_self on perfiles for select using (id = auth.uid());
create policy perfiles_update_self on perfiles for update using (id = auth.uid()) with check (id = auth.uid() and rol = (select rol from perfiles where id = auth.uid()));

-- ---------------------------------------------------------------
-- cursos: el docente dueño gestiona; el estudiante inscrito solo lee
-- ---------------------------------------------------------------
drop policy if exists cursos_docente_manage on cursos;
drop policy if exists cursos_public_select on cursos;
create policy cursos_select on cursos for select using (docente_id = auth.uid() or public.esta_inscrito(id));
create policy cursos_insert on cursos for insert with check (docente_id = auth.uid() and public.mi_rol() = 'docente');
create policy cursos_update on cursos for update using (docente_id = auth.uid()) with check (docente_id = auth.uid());
create policy cursos_delete on cursos for delete using (docente_id = auth.uid());

-- ---------------------------------------------------------------
-- inscripciones_curso
-- ---------------------------------------------------------------
alter table inscripciones_curso enable row level security;
drop policy if exists inscripciones_select on inscripciones_curso;
drop policy if exists inscripciones_docente_manage on inscripciones_curso;
drop policy if exists inscripciones_estudiante_update on inscripciones_curso;
create policy inscripciones_select on inscripciones_curso for select using (estudiante_id = auth.uid() or public.es_docente_de(curso_id));
create policy inscripciones_docente_manage on inscripciones_curso for all using (public.es_docente_de(curso_id)) with check (public.es_docente_de(curso_id));
-- el estudiante puede ajustar sus propias preferencias e idioma
create policy inscripciones_estudiante_update on inscripciones_curso for update using (estudiante_id = auth.uid()) with check (estudiante_id = auth.uid());

-- ---------------------------------------------------------------
-- sesiones_material: docente dueño gestiona; inscrito lee solo lo publicado
-- ---------------------------------------------------------------
drop policy if exists sesiones_public on sesiones_material;
drop policy if exists sesiones_docente_manage on sesiones_material;
create policy sesiones_select on sesiones_material for select using (public.es_docente_de(curso_id) or (estado = 'publicado' and public.esta_inscrito(curso_id)));
create policy sesiones_docente_manage on sesiones_material for all using (public.es_docente_de(curso_id)) with check (public.es_docente_de(curso_id));

-- ---------------------------------------------------------------
-- jobs: solo lectura para el docente dueño (la escritura la hace el backend)
-- ---------------------------------------------------------------
drop policy if exists jobs_service on jobs;
drop policy if exists jobs_docente_select on jobs;
create policy jobs_docente_select on jobs for select using (public.es_docente_de(public.curso_de_sesion(sesion_id)));

-- ---------------------------------------------------------------
-- paquetes_formato: docente lee/edita; inscrito lee si la sesión está publicada
-- ---------------------------------------------------------------
drop policy if exists paquetes_service on paquetes_formato;
drop policy if exists paquetes_docente_update on paquetes_formato;
drop policy if exists paquetes_select on paquetes_formato;
create policy paquetes_select on paquetes_formato for select using (
  public.es_docente_de(public.curso_de_sesion(sesion_id))
  or (public.sesion_publicada(sesion_id) and public.esta_inscrito(public.curso_de_sesion(sesion_id)))
);
create policy paquetes_docente_update on paquetes_formato for update
  using (public.es_docente_de(public.curso_de_sesion(sesion_id)))
  with check (public.es_docente_de(public.curso_de_sesion(sesion_id)));

-- ---------------------------------------------------------------
-- cache_ia: solo backend (sin políticas para usuarios)
-- ---------------------------------------------------------------
alter table cache_ia enable row level security;

-- ---------------------------------------------------------------
-- interacciones_progreso: el estudiante registra las suyas; el docente lee las de sus cursos
-- ---------------------------------------------------------------
alter table interacciones_progreso enable row level security;
drop policy if exists interacciones_insert on interacciones_progreso;
drop policy if exists interacciones_select on interacciones_progreso;
create policy interacciones_insert on interacciones_progreso for insert with check (estudiante_id = auth.uid());
create policy interacciones_select on interacciones_progreso for select using (estudiante_id = auth.uid() or public.es_docente_de(public.curso_de_sesion(sesion_id)));

-- ---------------------------------------------------------------
-- chat: cada estudiante ve solo sus conversaciones y mensajes
-- ---------------------------------------------------------------
drop policy if exists conversaciones_owner on conversaciones_chat;
drop function if exists public.conversacion_owner_check(uuid);
create policy conversaciones_owner on conversaciones_chat for all using (estudiante_id = auth.uid()) with check (estudiante_id = auth.uid());

drop policy if exists mensajes_participant on mensajes_chat;
create policy mensajes_participant on mensajes_chat for all
  using (exists (select 1 from conversaciones_chat cc where cc.id = conversacion_id and cc.estudiante_id = auth.uid()))
  with check (exists (select 1 from conversaciones_chat cc where cc.id = conversacion_id and cc.estudiante_id = auth.uid()));

drop policy if exists quota_owner on chat_cuota_diaria;
create policy quota_owner_select on chat_cuota_diaria for select using (estudiante_id = auth.uid());

-- ---------------------------------------------------------------
-- Índices útiles para las consultas frecuentes
-- ---------------------------------------------------------------
create index if not exists idx_sesiones_curso on sesiones_material(curso_id);
create index if not exists idx_jobs_sesion on jobs(sesion_id);
create index if not exists idx_jobs_estado on jobs(estado);
create index if not exists idx_inscripciones_estudiante on inscripciones_curso(estudiante_id);
create index if not exists idx_interacciones_sesion on interacciones_progreso(sesion_id);
