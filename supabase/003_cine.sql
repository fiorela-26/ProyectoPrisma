-- Nivel educativo CINE (UNESCO) en cursos: código + etiqueta oficial.
alter table cursos add column if not exists nivel_educativo text;
alter table cursos add column if not exists nivel_educativo_etiqueta text;

alter table cursos drop constraint if exists cursos_nivel_cine_check;
alter table cursos add constraint cursos_nivel_cine_check check (
  nivel_educativo is null or nivel_educativo in (
    'cine_1_inicial',
    'cine_1_avanzada',
    'cine_2',
    'cine_3',
    'cine_6'
  )
);
