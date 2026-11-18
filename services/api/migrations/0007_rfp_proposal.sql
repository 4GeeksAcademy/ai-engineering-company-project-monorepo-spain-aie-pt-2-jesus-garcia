-- Hito 9, Parte 2 — generación y evaluación de propuestas por departamento.
-- Migración aditiva e idempotente. Aplicar por conexión directa/session pooler
-- (5432), nunca por el transaction pooler (6543).

begin;

-- --- Ticket: payload de la propuesta y estado del job -----------------------

alter table public.rfp_ticket
  add column if not exists proposal_status character varying(40),
  add column if not exists proposal_stage character varying(60),
  add column if not exists proposal_payload jsonb,
  add column if not exists proposal_ready_at timestamp with time zone,
  add column if not exists proposal_task_id character varying(64),
  add column if not exists proposal_error character varying(2000);

alter table public.rfp_ticket
  drop constraint if exists ck_rfp_ticket_status;

alter table public.rfp_ticket
  add constraint ck_rfp_ticket_status check (
    status in (
      'analizando',
      'analisis_completo',
      'descartado',
      'error',
      'generando_borrador',
      'en_evaluación',
      'needs_human_review',
      'esperando_aprobación'
    )
  );

create index if not exists ix_rfp_ticket_proposal_status
  on public.rfp_ticket (proposal_status);

-- --- Sección: borrador, iteraciones y revisión humana -----------------------

alter table public.rfp_department_section
  add column if not exists draft_payload jsonb,
  add column if not exists generation_status character varying(40),
  add column if not exists iteration_count integer not null default 0,
  add column if not exists needs_human_review boolean not null default false,
  add column if not exists review_reason text,
  add column if not exists last_feedback text;

create index if not exists ix_rfp_department_section_status
  on public.rfp_department_section (generation_status);

-- --- Histórico del ciclo generador-evaluador --------------------------------

create table if not exists public.rfp_section_evaluation (
  id bigserial primary key,
  ticket_id character varying(36) not null
    references public.rfp_ticket(id) on delete cascade,
  department_id character varying(20) not null,
  iteration integer not null default 1,
  overall_pass boolean not null default false,
  readability jsonb not null default '{}'::jsonb,
  relevance jsonb not null default '{}'::jsonb,
  compliance jsonb not null default '{}'::jsonb,
  feedback text,
  created_at timestamp with time zone not null default now(),
  constraint uq_rfp_section_evaluation_ticket_department_iteration
    unique (ticket_id, department_id, iteration)
);

create index if not exists ix_rfp_section_evaluation_ticket
  on public.rfp_section_evaluation (ticket_id, department_id);

commit;
