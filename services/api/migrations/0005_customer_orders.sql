-- 0005_customer_orders.sql
-- Tabla mínima de propiedad de pedidos para el guard de autorización por
-- sesión del agente de CX. Aditiva e idempotente.

begin;

create table if not exists public.customer_order (
    id serial primary key,
    order_ref varchar(40) not null unique,
    owner_user_id varchar(64),
    owner_email varchar(255) not null,
    country varchar(2) not null check (country in ('US', 'ES')),
    carrier varchar(40) not null default '',
    status varchar(40) not null default '',
    delivered_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_customer_order_owner_email
    on public.customer_order (owner_email);

commit;
