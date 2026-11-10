-- G1–G4: outbox, cliente por SKU, umbral de stock y discrepancia estructurada.
-- Migración aditiva e idempotente. Se puede aplicar con el API desplegado.
-- Aplicar por conexión directa/session pooler (5432), no por el transaction
-- pooler (6543).

begin;

-- G1 — outbox transaccional
create schema if not exists ops;

create table if not exists ops.telemetry_outbox (
  id bigserial primary key,
  event_id character varying not null unique,
  payload jsonb not null,
  created_at timestamp with time zone not null default now(),
  sent_at timestamp with time zone,
  attempts integer not null default 0,
  last_error character varying
);

-- G2 / G3 — configuración por SKU (nullable hasta que exista el mapeo)
alter table public.sku add column if not exists client_id text;
alter table public.sku add column if not exists min_stock integer;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'ck_sku_min_stock'
  ) then
    alter table public.sku
      add constraint ck_sku_min_stock
      check (min_stock is null or min_stock >= 0);
  end if;
end
$$;

create index if not exists ix_sku_client_id on public.sku (client_id);

-- Snapshot de cliente en órdenes (para backfill y auditoría)
alter table public.stock_entry add column if not exists client_id text;
alter table public.stock_exit add column if not exists client_id text;

-- G4 — detalle de discrepancias (el evento se emite una vez por order_id)
create table if not exists public.inventory_discrepancy (
  id uuid primary key default gen_random_uuid(),
  order_id text not null,
  sku_id integer not null references public.sku(id),
  warehouse text not null,
  client_id text,
  system_quantity integer not null,
  physical_quantity integer not null,
  discrepancy_delta integer not null,
  incident_id text,
  created_at timestamp with time zone not null default now(),
  constraint uq_inventory_discrepancy_order_sku unique (order_id, sku_id)
);

create index if not exists ix_inventory_discrepancy_order
  on public.inventory_discrepancy (order_id);

create index if not exists ix_inventory_discrepancy_created_at
  on public.inventory_discrepancy (created_at);

commit;
