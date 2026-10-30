-- 0002: job_runs — ciclo de vida de los procesos en segundo plano (cron).
-- Migración aditiva e idempotente. Se puede aplicar con la API desplegada.
-- Aplicar por conexión directa/session pooler (5432), nunca por el transaction
-- pooler (6543). Ver README.md para backup, aplicación y rollback.
--
-- Capas distintas: `job_runs` audita intentos de disparo (cron → uno por día);
-- `reporting.pipeline_runs` audita ejecuciones del pipeline (una por semana).
-- No se fusionan ni se referencian entre sí.

begin;

create table if not exists public.job_runs (
  id            bigserial primary key,
  job_name      text        not null,
  target_date   date        not null,
  status        text        not null default 'pending',
  started_at    timestamptz,
  finished_at   timestamptz,
  error_message text,
  created_at    timestamptz not null default now()
);

-- Valores permitidos por la máquina de estados.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'ck_job_runs_status'
  ) then
    alter table public.job_runs
      add constraint ck_job_runs_status
      check (status in ('pending', 'processing', 'completed', 'failed'));
  end if;
end $$;

-- Idempotencia por día: consultas por (job_name, target_date).
create index if not exists ix_job_runs_job_target
  on public.job_runs (job_name, target_date);

-- Lock vía estado: como máximo una ejecución 'processing' por job_name.
create unique index if not exists ux_job_runs_processing
  on public.job_runs (job_name)
  where status = 'processing';

-- Idempotencia: como máximo un 'completed' por (job_name, target_date).
create unique index if not exists ux_job_runs_completed
  on public.job_runs (job_name, target_date)
  where status = 'completed';

-- Reconciliación de huérfanos (processing antiguos).
create index if not exists ix_job_runs_status_started
  on public.job_runs (status, started_at);

commit;
