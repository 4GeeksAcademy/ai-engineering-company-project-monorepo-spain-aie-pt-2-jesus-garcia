-- Hito 9, Parte 3 — aprobación humana por departamento y cierre.
-- Migración aditiva e idempotente. Aplicar por conexión directa/session
-- pooler (5432), nunca por el transaction pooler (6543).

begin;

-- --- Ticket: run de aprobación y estado de cierre ---------------------------

alter table public.rfp_ticket
  add column if not exists approval_status character varying(40),
  add column if not exists approval_thread_id character varying(120),
  add column if not exists approval_run integer not null default 0,
  add column if not exists approval_task_id character varying(64),
  add column if not exists approval_started_at timestamp with time zone,
  add column if not exists approval_completed_at timestamp with time zone,
  add column if not exists approval_error character varying(2000);

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
      'esperando_aprobación',
      'terminado'
    )
  );

create index if not exists ix_rfp_ticket_approval_status
  on public.rfp_ticket (approval_status);

-- --- Sección: paquete y decisión humana ------------------------------------

alter table public.rfp_department_section
  add column if not exists approval_comment character varying(4000),
  add column if not exists approval_decided_at timestamp with time zone,
  add column if not exists approval_round integer not null default 0,
  add column if not exists approval_interrupt_id character varying(64),
  add column if not exists approval_packet jsonb;

create index if not exists ix_rfp_department_section_approval
  on public.rfp_department_section (ticket_id, approval_status);

-- --- Traza por ejecución de nodo -------------------------------------------

create table if not exists public.rfp_node_trace (
  id bigserial primary key,
  ticket_id character varying(36) not null
    references public.rfp_ticket(id) on delete cascade,
  event_id character varying(36) not null unique,
  thread_id character varying(120) not null,
  part integer not null default 3,
  sequence integer not null default 0,
  node character varying(80) not null,
  agent character varying(120),
  department_id character varying(20),
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  occurred_at timestamp with time zone not null default now(),
  duration_ms integer,
  created_at timestamp with time zone not null default now()
);

create index if not exists ix_rfp_node_trace_ticket_sequence
  on public.rfp_node_trace (ticket_id, sequence);

-- --- Arbitraje --------------------------------------------------------------

create table if not exists public.rfp_arbitration (
  id bigserial primary key,
  ticket_id character varying(36) not null
    references public.rfp_ticket(id) on delete cascade,
  round integer not null default 1,
  trigger_id character varying(40) not null,
  arbitrator character varying(120),
  rule text,
  affected_sections jsonb not null default '[]'::jsonb,
  resolution jsonb not null default '{}'::jsonb,
  resolved boolean not null default false,
  created_at timestamp with time zone not null default now()
);

create index if not exists ix_rfp_arbitration_ticket_round
  on public.rfp_arbitration (ticket_id, round);

-- --- Documento final --------------------------------------------------------

create table if not exists public.rfp_final_document (
  id bigserial primary key,
  ticket_id character varying(36) not null unique
    references public.rfp_ticket(id) on delete cascade,
  contract_version character varying(40) not null default 'rfp-final-v1',
  currency character varying(3),
  sections jsonb not null default '[]'::jsonb,
  approved_by jsonb not null default '[]'::jsonb,
  markdown text not null default '',
  document_path character varying(1024),
  generated_at timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now()
);

commit;
