-- Tiempo real (Parte 1) — read model del SLA de entrega por país.
-- Alimenta la alerta de umbral de negocio `sla_threshold_alert`
-- (regla del briefing: < 90 % en US o España).
-- Migración aditiva e idempotente.

begin;

create schema if not exists reporting;

create table if not exists reporting.delivery_sla_weekly (
  id varchar(36) primary key,
  week_start date not null,
  country varchar(20) not null,
  warehouse varchar(64) not null,
  total_shipments integer not null default 0,
  on_time_shipments integer not null default 0,
  computed_at timestamp with time zone not null default now(),
  constraint uq_delivery_sla_week_country unique (week_start, country),
  constraint ck_delivery_sla_total check (total_shipments >= 0),
  constraint ck_delivery_sla_on_time check (on_time_shipments >= 0),
  constraint ck_delivery_sla_on_time_le_total
    check (on_time_shipments <= total_shipments)
);

create index if not exists ix_delivery_sla_week
  on reporting.delivery_sla_weekly (week_start);

comment on table reporting.delivery_sla_weekly is
  'SLA de entrega a tiempo por país y semana (feed de última milla).';

commit;
