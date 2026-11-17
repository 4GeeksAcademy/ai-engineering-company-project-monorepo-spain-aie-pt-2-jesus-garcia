-- Hito 9, Parte 1 — Recepción de RFPs.
-- Migración aditiva e idempotente. Aplicar por conexión directa/session pooler
-- (5432), nunca por el transaction pooler (6543).

begin;

create table if not exists public.rfp_ticket (
  id character varying(36) primary key,
  rfp_id character varying(40) not null unique,
  status character varying(40) not null default 'analizando',
  pipeline_stage character varying(60),
  raw_pdf_path character varying(1024) not null,
  markdown_path character varying(1024),
  original_filename character varying(255) not null,
  file_sha256 character varying(64) not null,
  celery_task_id character varying(64),
  classification jsonb,
  discard_reason character varying(2000),
  error_message character varying(2000),
  handoff_status character varying(20) not null default 'none',
  handoff_payload jsonb,
  handoff_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint ck_rfp_ticket_status check (
    status in ('analizando', 'analisis_completo', 'descartado', 'error')
  ),
  constraint ck_rfp_ticket_handoff check (
    handoff_status in ('none', 'ready')
  )
);

create index if not exists ix_rfp_ticket_status on public.rfp_ticket (status);
create index if not exists ix_rfp_ticket_sha256 on public.rfp_ticket (file_sha256);
create index if not exists ix_rfp_ticket_status_created
  on public.rfp_ticket (status, created_at);

create table if not exists public.rfp_metadata (
  id bigserial primary key,
  ticket_id character varying(36) not null unique references public.rfp_ticket(id) on delete cascade,
  client_name character varying(255),
  client_country character varying(20),
  currency character varying(3),
  language character varying(5),
  services_requested jsonb not null default '[]'::jsonb,
  departments_needed jsonb not null default '[]'::jsonb,
  monthly_volume integer,
  deadline date,
  budget_range character varying(255),
  extraction jsonb not null default '{}'::jsonb,
  readability_metrics jsonb not null default '{}'::jsonb,
  document_metadata jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create index if not exists ix_rfp_metadata_ticket_id
  on public.rfp_metadata (ticket_id);

create table if not exists public.rfp_department_section (
  id bigserial primary key,
  ticket_id character varying(36) not null references public.rfp_ticket(id) on delete cascade,
  department_id character varying(20) not null,
  responsible character varying(120),
  key_aspects jsonb not null default '[]'::jsonb,
  open_questions jsonb not null default '[]'::jsonb,
  assumed_facts jsonb not null default '{}'::jsonb,
  unsupported_claims jsonb not null default '[]'::jsonb,
  draft_content text,
  evaluation_results jsonb,
  approval_status character varying(40),
  approver character varying(120),
  approved_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint uq_rfp_department_section_ticket_department
    unique (ticket_id, department_id),
  constraint ck_rfp_department_section_department check (
    department_id in ('warehouse', 'lastmile', 'reverse')
  )
);

create index if not exists ix_rfp_department_section_ticket
  on public.rfp_department_section (ticket_id);

commit;
