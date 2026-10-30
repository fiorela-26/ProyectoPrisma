-- schema for sistema_inclusivo
create extension if not exists pgcrypto;

create table if not exists perfiles (
  id uuid primary key references auth.users on delete cascade,
  nombre text not null,
  rol text not null check (rol in ('docente','estudiante')),
  creado_en timestamptz default now()
);

create table if not exists cursos (
  id uuid primary key default gen_random_uuid(),
  docente_id uuid not null references perfiles(id),
  nombre_curso text not null,
  descripcion text,
  nivel_educativo text,
  nivel_educativo_etiqueta text,
  creado_en timestamptz default now(),
  constraint cursos_nivel_cine_check check (
    nivel_educativo is null or nivel_educativo in (
      'cine_1_inicial',
      'cine_1_avanzada',
      'cine_2',
      'cine_3',
      'cine_6'
    )
  )
);

create table if not exists inscripciones_curso (
  id uuid primary key default gen_random_uuid(),
  curso_id uuid references cursos(id) on delete cascade,
  estudiante_id uuid references perfiles(id),
  preferencias text[] default '{}',
  idioma_preferido text default 'es',
  unique (curso_id, estudiante_id)
);

create table if not exists sesiones_material (
  id uuid primary key default gen_random_uuid(),
  curso_id uuid references cursos(id) on delete cascade,
  titulo text not null,
  archivo_url text,
  tipo_archivo text,
  contenido_hash text,
  idioma_original text,
  texto_extraido text,
  estado text default 'procesando' check (estado in ('procesando','revision','publicado','error')),
  creado_en timestamptz default now()
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  tipo text not null,
  sesion_id uuid references sesiones_material(id) on delete cascade,
  formato text,
  estado text not null default 'queued' check (estado in ('queued','running','done','failed')),
  intentos int default 0,
  progreso int default 0,
  error text,
  creado_en timestamptz default now(),
  iniciado_en timestamptz,
  terminado_en timestamptz
);

create table if not exists paquetes_formato (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid references sesiones_material(id) on delete cascade,
  formato text not null,
  contenido jsonb not null,
  generado_por_ia boolean default true,
  editado_por_docente boolean default false,
  modelo_usado text,
  version int default 1,
  unique (sesion_id, formato)
);

create table if not exists cache_ia (
  clave text primary key,
  formato text,
  contenido jsonb,
  creado_en timestamptz default now()
);

create table if not exists interacciones_progreso (
  id uuid primary key default gen_random_uuid(),
  estudiante_id uuid references perfiles(id),
  sesion_id uuid references sesiones_material(id),
  formato_usado text,
  duracion_segundos int,
  completado boolean default false,
  creado_en timestamptz default now()
);

create table if not exists conversaciones_chat (
  id uuid primary key default gen_random_uuid(),
  sesion_id uuid references sesiones_material(id) on delete cascade,
  estudiante_id uuid references perfiles(id),
  creado_en timestamptz default now()
);

create table if not exists mensajes_chat (
  id uuid primary key default gen_random_uuid(),
  conversacion_id uuid references conversaciones_chat(id) on delete cascade,
  rol text check (rol in ('user','assistant')),
  contenido text not null,
  creado_en timestamptz default now()
);

create table if not exists chat_cuota_diaria (
  estudiante_id uuid references perfiles(id),
  fecha date default current_date,
  mensajes int default 0,
  primary key (estudiante_id, fecha)
);

-- RLS y policies
alter table perfiles enable row level security;
drop policy if exists perfiles_user_self on perfiles;
create policy perfiles_user_self on perfiles for all using (auth.uid() = id) with check (auth.uid() = id);
drop policy if exists perfiles_service_role on perfiles;
create policy perfiles_service_role on perfiles for all using (auth.role() = 'service_role');

alter table cursos enable row level security;
drop policy if exists cursos_docente_manage on cursos;
create policy cursos_docente_manage on cursos for all using (auth.role() = 'service_role' or exists (select 1 from perfiles p where p.id = auth.uid() and p.rol = 'docente')) with check (auth.role() = 'service_role' or exists (select 1 from perfiles p where p.id = auth.uid() and p.rol = 'docente'));
drop policy if exists cursos_public_select on cursos;
create policy cursos_public_select on cursos for select using (true);

alter table sesiones_material enable row level security;
drop policy if exists sesiones_public on sesiones_material;
create policy sesiones_public on sesiones_material for select using (estado = 'publicado' or auth.role() = 'service_role' or exists (select 1 from cursos c where c.id = sesiones_material.curso_id and c.docente_id = auth.uid()));
drop policy if exists sesiones_docente_manage on sesiones_material;
create policy sesiones_docente_manage on sesiones_material for all using (auth.role() = 'service_role' or exists (select 1 from cursos c where c.id = sesiones_material.curso_id and c.docente_id = auth.uid())) with check (auth.role() = 'service_role' or exists (select 1 from cursos c where c.id = sesiones_material.curso_id and c.docente_id = auth.uid()));

alter table jobs enable row level security;
drop policy if exists jobs_service on jobs;
create policy jobs_service on jobs for all using (auth.role() = 'service_role');

alter table paquetes_formato enable row level security;
drop policy if exists paquetes_service on paquetes_formato;
create policy paquetes_service on paquetes_formato for all using (auth.role() = 'service_role');
drop policy if exists paquetes_docente_update on paquetes_formato;
create policy paquetes_docente_update on paquetes_formato for update using (auth.role() = 'service_role' or exists (select 1 from sesiones_material s join cursos c on c.id = s.curso_id where paquetes_formato.sesion_id = s.id and c.docente_id = auth.uid())) with check (true);

alter table conversaciones_chat enable row level security;
create or replace function public.conversacion_owner_check(cid uuid) returns boolean language sql as $$ select exists (select 1 from conversaciones_chat cc where cc.id = cid and cc.estudiante_id = auth.uid()) $$;
drop policy if exists conversaciones_owner on conversaciones_chat;
create policy conversaciones_owner on conversaciones_chat for all using (auth.role() = 'service_role' or public.conversacion_owner_check(id));

alter table mensajes_chat enable row level security;
drop policy if exists mensajes_participant on mensajes_chat;
create policy mensajes_participant on mensajes_chat for all using (auth.role() = 'service_role' or exists (select 1 from conversaciones_chat cc where cc.id = mensajes_chat.conversacion_id and cc.estudiante_id = auth.uid())) with check (true);

alter table chat_cuota_diaria enable row level security;
drop policy if exists quota_owner on chat_cuota_diaria;
create policy quota_owner on chat_cuota_diaria for all using (auth.role() = 'service_role' or estudiante_id = auth.uid()) with check (auth.role() = 'service_role' or estudiante_id = auth.uid());

-- trigger to create perfil on auth.users insert
create or replace function public.create_profile_if_not_exists() returns trigger language plpgsql as $$
begin
  insert into public.perfiles (id, nombre, rol)
  values (new.id, coalesce(new.raw_user_meta->>'full_name', new.email), 'estudiante')
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.create_profile_if_not_exists();

-- end
