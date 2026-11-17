-- 0004_agent_memory.sql — memoria persistente del agente (TrackFlow)
--
-- Store separado del RAG. No crea ni modifica ninguna colección de Qdrant ni
-- la tabla/almacén de conocimiento de la empresa. Aditiva e idempotente.
--
-- Aplicar por conexión directa o session pooler (5432), nunca por el
-- transaction pooler (6543). Ver migrations/README.md.

create table if not exists public.agent_memory_entries (
    id                  text primary key,
    memory_type         text not null,
    scope_type          text not null,
    scope_key           text not null,
    scope_label         text not null default '',
    scope_json          jsonb not null default '{}'::jsonb,
    fact                text not null,
    reason              text,
    status              text not null default 'active',
    version             integer not null default 1,
    supersedes_id       text,
    source_proposal_id  text,
    created_by          text not null,
    approved_by         text not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    expires_at          timestamptz,
    review_at           timestamptz,
    constraint ck_agent_memory_entry_type
        check (memory_type in ('carrier_rule', 'operational_context', 'client_preference')),
    constraint ck_agent_memory_entry_scope
        check (scope_type in ('carrier', 'ops', 'client')),
    constraint ck_agent_memory_entry_status
        check (status in ('active', 'superseded', 'expired', 'stale', 'retired', 'blocked'))
);

create index if not exists ix_agent_memory_entries_scope_status
    on public.agent_memory_entries (scope_key, status);
create index if not exists ix_agent_memory_entries_type_status
    on public.agent_memory_entries (memory_type, status);
create index if not exists ix_agent_memory_entries_review
    on public.agent_memory_entries (status, review_at);
-- Una sola regla activa por alcance; el histórico queda versionado.
create unique index if not exists ux_agent_memory_active_scope
    on public.agent_memory_entries (scope_key)
    where status = 'active';

create table if not exists public.agent_memory_proposals (
    id                   text primary key,
    session_id           text not null,
    user_id              text not null,
    run_id               text,
    memory_type          text not null,
    scope_type           text not null,
    scope_key            text not null,
    scope_label          text not null default '',
    scope_json           jsonb not null default '{}'::jsonb,
    fact                 text not null,
    reason               text,
    source_quote         text not null default '',
    status               text not null default 'pending',
    decision_label       text,
    decision_confidence  double precision,
    decision_message     text,
    decision_at          timestamptz,
    resulting_entry_id   text,
    validation_code      text,
    validation_detail    text,
    created_at           timestamptz not null default now(),
    expires_at           timestamptz not null,
    constraint ck_agent_memory_proposal_type
        check (memory_type in ('carrier_rule', 'operational_context', 'client_preference')),
    constraint ck_agent_memory_proposal_scope
        check (scope_type in ('carrier', 'ops', 'client')),
    constraint ck_agent_memory_proposal_status
        check (status in ('pending', 'approved', 'rejected', 'edited', 'blocked', 'expired'))
);

create index if not exists ix_agent_memory_proposals_user_created
    on public.agent_memory_proposals (user_id, created_at);
create index if not exists ix_agent_memory_proposals_session
    on public.agent_memory_proposals (session_id);
create index if not exists ix_agent_memory_proposals_status
    on public.agent_memory_proposals (status);
-- Una sola propuesta pendiente por usuario, reforzado en base de datos.
create unique index if not exists ux_agent_memory_pending_user
    on public.agent_memory_proposals (user_id)
    where status = 'pending';

create table if not exists public.agent_memory_audit (
    id                   bigserial primary key,
    at                   timestamptz not null default now(),
    actor_user_id        text,
    session_id           text,
    action               text not null,
    proposal_id          text,
    entry_id             text,
    origin_message       text,
    origin_message_hash  text,
    detail               jsonb not null default '{}'::jsonb
);

create index if not exists ix_agent_memory_audit_at
    on public.agent_memory_audit (at);
create index if not exists ix_agent_memory_audit_action
    on public.agent_memory_audit (action);
create index if not exists ix_agent_memory_audit_proposal
    on public.agent_memory_audit (proposal_id);
create index if not exists ix_agent_memory_audit_entry
    on public.agent_memory_audit (entry_id);

-- Rollback:
-- drop table if exists public.agent_memory_audit;
-- drop table if exists public.agent_memory_proposals;
-- drop table if exists public.agent_memory_entries;
