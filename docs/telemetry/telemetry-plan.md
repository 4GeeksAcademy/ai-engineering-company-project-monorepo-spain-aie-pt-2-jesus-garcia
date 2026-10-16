# TrackFlow — Telemetry Plan

> **Status:** design deliverable (no runtime instrumentation in this iteration).
> **Scope:** inventory management system of TrackFlow (warehouses Los Angeles & Zaragoza) plus the
> backoffice sections around it (authentication, performance, frontend errors, navigation).
> **Companion file:** [`event-schemas.json`](./event-schemas.json) — machine-readable Event Envelope
> and per-event `properties` allowlists.

---

## 1. Objectives

Design the telemetry layer that:

1. Captures the **mandatory inventory metrics** end-to-end so they can later feed Ana's warehouse
   operations dashboard and Thomas's global executive dashboard (volume and SLA comparison between
   the US and Spain).
2. Extends coverage to the rest of the backoffice (auth, performance, frontend errors, navigation)
   without collecting personal data.
3. Produces events that **someone else can consume later without asking us how they work** — hence a
   strict envelope, versioned schemas and per-event property allowlists.
4. Decides, per event, whether it must be processed as a **stream** or as a **batch**, and how
   high-frequency events are throttled.

Aggregation axes required from day one: **warehouse**, **client** and **country** (Los Angeles → USA,
Zaragoza → Spain).

## 2. The golden rule

Every event must complete this sentence, otherwise it does not exist:

> _We capture **[event_type]** because we need to know **[hypothesis]**, which lets us take
> **[concrete decision]**._

The rule is applied per event in §5.2 and encoded in `event-schemas.json` as the `golden_rule` field.

## 3. Prerequisites — data model gaps

The mandatory `properties` for inventory events require fields that **do not exist yet** in the
current data model. They are documented here as prerequisites; the plan assumes they will be added
to the inventory model (decision taken with the developer).

| Missing field | Where it belongs | Used by | Note |
|---|---|---|---|
| `client_id` | `SKU` ORM (`services/api/models.py:293`) | all inventory events | Each SKU belongs to exactly one client (business rule). Today the ORM only has `name`, `sku_code`, `warehouse`. |
| `product_category` | `SKU` ORM | all inventory events | Values: `fashion`, `electronics`, `cosmetics` (moda / electrónica / cosmética). |
| `min_stock` | per `SKU` (or per `client` × `SKU`) | `stock_threshold_triggered` | No configurable threshold exists today; the event cannot fire without it. |
| `country` | derivable from `warehouse` | aggregation | `los_angeles → USA`, `zaragoza → Spain`. Derived, never stored twice. |

Additional structural gaps that shape instrumentation:

- **No direct stock-edit endpoint exists.** Stock is only mutated through
  `POST /inventory/orders/inbound|outbound` (`services/api/app/routes/inventory.py`). Therefore
  `direct_stock_edit_rejected` is defined as a **guard**: it fires when a request that would mutate
  stock outside an order is rejected (e.g. a future `PUT /inventory/products/{id}` carrying a stock
  field, a raw SQL/admin path, or a `405`/`400` guard). It is the tripwire that proves the
  "stock is never edited directly" rule is enforced.
- **No physical count / audit feature exists.** `inventory_discrepancy_detected` is anchored to the
  existing incident manager: when an incident with `category = "inventory_discrepancy"` is created
  (`services/api/app/routes/incidents_manager.py:184`). This reuses a real, already-instrumented
  domain signal instead of inventing a parallel one.
- **Only a log line exists for latency.** `timing_middleware` (`services/api/app/main.py:53`) already
  computes `method`, `path`, `status_code` and `duration_ms` and writes them to a log. The
  `api_response_time` event reuses exactly that data as structured telemetry.

## 4. Phase 1 — Exhaustive data opportunity catalog

### 4.1 Inventory management flow (as implemented)

```
[Backoffice user]
  │
  ├─ /login ──► POST /api/auth/login ──► JWT stored in localStorage (trackflow_token)
  │
  ├─ AuthProvider mount ──► GET /api/auth/me  (token validation)
  │        ├─ 401 → token cleared → redirect /login
  │        └─ network error → sessionError + retry
  │
  └─ /inventory (protected layout)
        ├─ fetchInventoryProducts(token)      GET /inventory/products
        ├─ fetchInventoryOrders(token)        GET /inventory/orders   (manager/admin only)
        ├─ open OrderForm (inbound/outbound)
        │     ├─ client validation: quantity > 0, warehouse present
        │     ├─ outbound → ConfirmDialog
        │     └─ POST /inventory/orders/{inbound|outbound}
        │            └─ inventory_service._validate_order_input
        │                   ├─ quantity <= 0        → 400
        │                   ├─ warehouse invalid    → 400
        │                   └─ SKU not found        → 404
        │            └─ create_outbound: check-then-write
        │                   └─ requested > available → 400 (no write)
        └─ reload() → re-fetch products + orders
```

### 4.2 Instrumentation points inside the flow (minimum 5)

| # | Point | Anchor (file:line) | Event |
|---|---|---|---|
| 1 | Direct stock modification attempt rejected | guard in `routes/inventory.py` (write paths) | `direct_stock_edit_rejected` |
| 2 | Failed validation (`quantity`, `warehouse`, `sku_id`) | `services/inventory_service.py:27` | `stock_validation_failed` |
| 3 | Outbound rejected for insufficient stock | `services/inventory_service.py:57` | `outbound_rejected_insufficient_stock` |
| 4 | Stock falls below configured minimum | new threshold check in `inventory_service` | `stock_threshold_triggered` |
| 5 | Physical count / audit discrepancy | `routes/incidents_manager.py:184` (`inventory_discrepancy`) | `inventory_discrepancy_detected` |
| 6 | Inbound / outbound order completed | `services/inventory_service.py:40` / `:54` | `inbound_order_created` / `outbound_order_created` |
| 7 | Order form opened / abandoned | `components/inventory/OrderForm.tsx:21` | `order_form_opened` / `order_form_abandoned` |

### 4.3 Authentication

| Point | Anchor | Event |
|---|---|---|
| Session begins | `contexts/AuthContext.tsx:55` | `session_started` |
| Login OK | `components/auth/LoginForm.tsx:27` → `POST /auth/login` | `login_succeeded` |
| Login rejected (`401`) | `components/auth/LoginForm.tsx:32` | `login_failed` |
| Token expired / invalid on mount or request | `AuthContext.tsx:77` | `session_expired` |

### 4.4 Performance

| Point | Anchor | Event |
|---|---|---|
| Every API response (latency + status) | `app/main.py:53` (middleware) | `api_response_time` |
| Frontend route load / navigation timing | client router + `useAsyncData` (`hooks/useAsyncData.ts`) | `page_view` (dwell) |

### 4.5 Unhandled frontend errors

| Point | Anchor | Event |
|---|---|---|
| `window.onerror` / `window.onunhandledrejection` | app root / error boundary | `frontend_error_uncaught` |

### 4.6 Navigation

| Point | Anchor | Event |
|---|---|---|
| Each route visit | `components/Sidebar.tsx` + router | `page_view` |
| Depth of navigation per session | derived | `pages_visited_in_session` |
| Order flow started but not completed | `OrderForm.tsx` open vs submit | `order_form_abandoned` |

### 4.7 Opportunity catalog (golden rule per event)

Every event below completes the golden rule of §2. Events are split into the two groups
required by the brief: **mandatory** (`obligatorio`, the contracted inventory metrics from the
company brief) and **identified opportunity** (`oportunidad identificada`, proposed during
exploration of the backoffice). The mandatory group is fixed; the opportunity group is ours to
extend and can be dropped without breaking the contracted metrics.

#### 4.7.1 Mandatory — `obligatorio`

| event_type | We capture it because we need to know… | …which lets us decide… |
|---|---|---|
| `inbound_order_created` | incoming volume per client / warehouse | warehouse capacity and staffing (Ana) |
| `outbound_order_created` | orders processed per client / warehouse and pace | detect bottlenecks before they hit SLA (Ana) |
| `stock_threshold_triggered` | how often a client runs out of a SKU (minimum-threshold activations) | alert client + commercial before a stockout (Miguel) |
| `direct_stock_edit_rejected` | whether staff try to bypass traceability | reinforce training/permissions where it happens most |
| `inventory_discrepancy_detected` | which SKUs / warehouses show most discrepancies | prioritize inventory audits (Ana) |

#### 4.7.2 Identified opportunity — `oportunidad identificada`

| event_type | We capture it because we need to know… | …which lets us decide… |
|---|---|---|
| `session_started` | when and how often sessions begin | adoption/usage analysis |
| `login_succeeded` | successful logins per role | adoption tracking and access baselines |
| `login_failed` | failed login attempts | detect credential stuffing / UX friction |
| `session_expired` | how often sessions die mid-task | tune token TTL and re-auth UX |
| `page_view` | which pages are visited and how often | prioritize UX investment (high frequency) |
| `pages_visited_in_session` | navigation depth per session | engagement and information-architecture tuning |
| `order_form_opened` | how many order flows start | funnel conversion measurement |
| `order_form_abandoned` | where operators abandon order creation | reduce friction in the order flow |
| `stock_validation_failed` | which validation errors happen | improve form guidance / fix systemic issues |
| `outbound_rejected_insufficient_stock` | how often outbound fails for lack of stock | inventory planning and client alerts |
| `incident_form_opened` | how many incident reports start | funnel conversion for the incident manager |
| `incident_created` | incident volume by category / branch / origin | prioritize root-cause work and staffing where incidents concentrate |
| `incident_validation_failed` | which incident fields fail validation | improve the incident form and fix systemic gaps |
| `incident_status_change_opened` | how often operators open the status flow | measure whether incidents actually move forward |
| `incident_status_changed` | how fast incidents move between states | reduce incident backlog / resolution time (SLA) |
| `incident_transition_rejected` | rejected state transitions and why | detect UX/permission friction and misused flows |
| `api_response_time` | API latency per endpoint | detect performance regressions (high frequency) |
| `frontend_error_uncaught` | unhandled JS errors and their routes | fix stability issues before users report them |

### 4.8 Incident management flow (as implemented)

The centralized incident manager (`/incidents`) is a real, already-shipped surface, so it is
instrumented alongside inventory. It reuses the domain enums already defined in
`services/api/models.py:217-248` (`origin`, `branch`, `category`, `status`,
`INCIDENT_STATUS_TRANSITIONS`).

```
[Backoffice user]
  │
  └─ /incidents (protected layout)
        ├─ fetchIncidents(token) + fetchIncidentSummary(token)   GET /api/incidents[/summary]
        │
        ├─ "+ Nueva incidencia" button ──► setShowForm(true) ──► IncidentForm
        │     ├─ client validate()  (title/description/origin/branch/category)
        │     ├─ ConfirmDialog
        │     └─ POST /api/incidents  ──► _validate_create
        │            ├─ missing/invalid field → 400
        │            └─ insert → 201
        │
        └─ "Cambiar estado" button ──► setFlowTarget(incident) ──► StatusFlowModal
              ├─ nextStatuses(current)  (same map as INCIDENT_STATUS_TRANSITIONS)
              ├─ ConfirmDialog
              └─ PATCH /api/incidents/{id}/status
                     ├─ invalid transition / final state → 400
                     └─ update status → 200
```

Instrumentation points inside the incident flow:

| # | Point | Anchor (file:line) | Event |
|---|---|---|---|
| 1 | Incident form opened | `uis/backoffice/app/(protected)/incidents/page.tsx:146` (`+ Nueva incidencia`) | `incident_form_opened` |
| 2 | Incident created | `services/api/app/routes/incidents_manager.py:194` (201) | `incident_created` |
| 3 | Incident create validation failed | `services/api/app/routes/incidents_manager.py:40` (`_validate_create`, 400) | `incident_validation_failed` |
| 4 | Status flow opened | `incidents/page.tsx:264` (`Cambiar estado`) → `StatusFlowModal.tsx:72` | `incident_status_change_opened` |
| 5 | Status changed | `StatusFlowModal.tsx:99` (confirm) → `incidents_manager.py:223` (200) | `incident_status_changed` |
| 6 | Transition rejected | `incidents_manager.py:244-254` (invalid transition / final state, 400) | `incident_transition_rejected` |

Business links:

- An incident whose `category = "inventory_discrepancy"` is the real, already-shipped trigger for
  the mandatory `inventory_discrepancy_detected` event (§4.2 #5). The two events are not
  duplicates: `incident_created` measures incident-manager usage; `inventory_discrepancy_detected`
  carries the inventory-specific `system_quantity` / `physical_quantity` / `discrepancy_delta`.
- "Activaciones del umbral mínimo" stay in the mandatory group as `stock_threshold_triggered`
  (§4.2 #4): no incident is required for it to fire.

## 5. Phase 2 — Event Envelope (EE) and event schemas

### 5.1 Standard envelope

Every event, frontend or backend, is wrapped in the same envelope. Domain data lives **only** inside
`properties`; nothing sensitive is allowed at envelope level.

| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | string (UUIDv4) | yes | Unique id, generated at emission. Idempotency key. |
| `timestamp` | string (ISO-8601, UTC) | yes | Emission time, e.g. `2026-10-05T20:34:00.000Z`. |
| `session_id` | string (UUID) | yes | Session/browsing id. Backend derives it from the request when absent. |
| `user_id` | string \| null | yes (nullable) | TinyDB user id. `null` for anonymous/pre-auth events. |
| `event_type` | string (enum) | yes | One of the event types in §5.2. |
| `schema_version` | string (semver) | yes | Version of the **properties** schema. Starts at `1.0.0`. |
| `request_id` | string (UUID) \| null | yes (nullable) | Correlation id for the originating request/flow. |
| `source` | enum `frontend` \| `backend` | yes | Where the event was produced. |
| `app` | enum `backoffice` \| `website` | yes | Product surface. |
| `properties` | object | yes | Event-specific payload; must satisfy the allowlist of that event. |

Design rules:

- **`event_type` is a closed enum.** Unknown types are rejected by the collector.
- **`schema_version` is per event type.** A breaking change to `properties` bumps the version; the
  consumer can branch on it.
- **`request_id`** ties an order flow together across frontend and backend (e.g. `order_form_opened`
  → `outbound_order_created`).
- **`country` is derived**, not sent: `los_angeles → USA`, `zaragoza → Spain`.

### 5.2 Event catalog and `properties` allowlist

Minimum inventory `properties` (mandatory events): `warehouse`, `client_id`, `product_id`,
`product_category`, `quantity`. No consumer personal data (final recipient), no carrier data.

#### Mandatory metrics

| event_type | Source | Processing | Allowed properties (allowlist) |
|---|---|---|---|
| `inbound_order_created` | backend | stream | `warehouse`, `client_id`, `product_id`, `product_category`, `quantity`, `order_id`, `available_after` |
| `outbound_order_created` | backend | stream | `warehouse`, `client_id`, `product_id`, `product_category`, `quantity`, `order_id`, `available_after` |
| `stock_threshold_triggered` | backend | stream | `warehouse`, `client_id`, `product_id`, `product_category`, `quantity`, `min_stock`, `deficit` |
| `direct_stock_edit_rejected` | backend | stream | `warehouse`, `client_id`, `product_id`, `product_category`, `attempted_quantity`, `rejection_reason`, `endpoint`, `user_role` |
| `inventory_discrepancy_detected` | backend | batch | `warehouse`, `client_id`, `product_id`, `product_category`, `quantity`, `system_quantity`, `physical_quantity`, `discrepancy_delta`, `detection_source`, `incident_id` |

#### Identified opportunity events (18)

The mandatory five are the `obligatorio` group of §4.7.1; the events below are the
`oportunidad identificada` group of §4.7.2.

| event_type | Source | Processing | Allowed properties (allowlist) |
|---|---|---|---|
| `session_started` | frontend | batch | `user_role`, `entry_path` |
| `login_succeeded` | frontend | batch | `user_role`, `method` |
| `login_failed` | frontend | stream | `failure_reason`, `method` |
| `session_expired` | frontend | batch | `reason`, `last_path`, `session_duration_seconds` |
| `page_view` | frontend | batch | `path`, `referrer_path`, `app`, `dwell_time_ms` |
| `pages_visited_in_session` | frontend | batch | `page_count`, `unique_page_count`, `top_path`, `session_duration_seconds` |
| `order_form_opened` | frontend | batch | `warehouse`, `order_type`, `product_id`, `product_category`, `client_id` |
| `order_form_abandoned` | frontend | batch | `warehouse`, `order_type`, `product_id`, `product_category`, `client_id`, `last_field_touched`, `time_in_form_ms`, `abandon_reason` |
| `stock_validation_failed` | backend | stream | `warehouse`, `product_id`, `client_id`, `product_category`, `field`, `reason`, `attempted_quantity`, `order_type` |
| `outbound_rejected_insufficient_stock` | backend | stream | `warehouse`, `client_id`, `product_id`, `product_category`, `requested_quantity`, `available_quantity`, `deficit` |
| `incident_form_opened` | frontend | batch | `entry_source` |
| `incident_created` | backend | stream | `incident_id`, `category`, `branch`, `origin`, `status`, `description_length` |
| `incident_validation_failed` | backend | stream | `field`, `reason`, `origin`, `branch`, `category` |
| `incident_status_change_opened` | frontend | batch | `incident_id`, `from_status`, `allowed_targets`, `category`, `branch` |
| `incident_status_changed` | backend | stream | `incident_id`, `from_status`, `to_status`, `category`, `branch`, `time_in_status_seconds` |
| `incident_transition_rejected` | backend | stream | `incident_id`, `from_status`, `attempted_status`, `reason`, `category`, `branch` |
| `api_response_time` | backend | batch | `method`, `path`, `status_code`, `duration_ms`, `app`, `cache_hit` |
| `frontend_error_uncaught` | frontend | stream | `error_type`, `error_name`, `error_message_sanitized`, `path`, `app` |

High-frequency frontend event: **`page_view`**. High-frequency backend event: **`api_response_time`**.

### 5.3 Privacy by design

- `login_failed` never carries the email or password — only a coarse `failure_reason`.
- `frontend_error_uncaught` carries a **sanitized, truncated** message and no full stack (stacks can
  leak tokens / PII). Store a `stack_hash` if grouping is needed.
- No `properties` contains final-recipient data (name, address, phone) — that belongs to last-mile
  tracking, explicitly out of scope.
- No raw IP, precise geolocation, or carrier identifiers.

## 6. Phase 3 — Delivery

### 6.1 Stream vs batch, with rationale

| event_type | Mode | Rationale |
|---|---|---|
| `inbound_order_created` | stream | Feeds Ana's near-real-time volume/ops view. |
| `outbound_order_created` | stream | Bottleneck/SLA detection needs low latency. |
| `stock_threshold_triggered` | stream | Triggers an immediate client/commercial alert. |
| `direct_stock_edit_rejected` | stream | Security/traceability tripwire; react quickly. |
| `inventory_discrepancy_detected` | batch | Drives weekly audit prioritization, not real-time action. |
| `session_started` | batch | Usage analytics, no operational urgency. |
| `login_succeeded` | batch | Adoption baselines; daily aggregation is enough. |
| `login_failed` | stream | Security: detect brute force / stuffing early. |
| `session_expired` | batch | UX tuning over time, not per-event action. |
| `page_view` | batch | High volume, product analytics; aggregate offline. |
| `pages_visited_in_session` | batch | Derived per session, computed at session end. |
| `order_form_opened` | batch | Funnel measurement, aggregated. |
| `order_form_abandoned` | batch | UX friction analysis, aggregated. |
| `stock_validation_failed` | stream | Repeated failures signal a systemic/broken form → act fast. |
| `outbound_rejected_insufficient_stock` | stream | Inventory planning / client alert with low latency. |
| `incident_form_opened` | batch | Funnel measurement for the incident manager; aggregated. |
| `incident_created` | stream | Incident inventory feeds operational triage (Ana) and the exec view; low latency. |
| `incident_validation_failed` | stream | Repeated failures signal a broken form → act fast. |
| `incident_status_change_opened` | batch | Usage/funnel measurement; aggregated, no live action. |
| `incident_status_changed` | stream | Resolution-time and backlog monitoring need low latency (SLA). |
| `incident_transition_rejected` | stream | Permission/UX friction tripwire; react quickly. |
| `api_response_time` | batch | High volume; latency percentiles computed in windows. |
| `frontend_error_uncaught` | stream | Stability alerting; users must not be the first to know. |

Rule of thumb: **stream when the event triggers an alert or feeds a live operational dashboard;
batch when it only feeds analysis, funnels, or high-volume aggregation.**

### 6.2 Throttle / debounce strategies for high-frequency events

| Event | Strategy |
|---|---|
| `page_view` | Debounce 500 ms per route + dedupe by `(session_id, path, 1s window)`. Emit one `page_view` per effective navigation, not per render. Sample at 100% for now; drop to 10–20% under peak if volume becomes a cost problem. |
| `api_response_time` | Do **not** emit per request. Aggregate in a 60 s window keyed by `(method, path, status_code)`, then flush one event per bucket with `duration_ms` = p50/p95 or count. In-process buffer, flush on timer or on size threshold. |
| `order_form_abandoned` | Debounce on `visibilitychange` / blur with a 30 s grace timer; cancel if the form is submitted or reopened. One event per abandoned flow, not per field. |
| `pages_visited_in_session` | Emit once per session, on `session_expired`, explicit logout, or a 30 min inactivity timeout. |
| `session_started` | One event per new session id; ignore re-renders (idempotent by `session_id`). |
| `frontend_error_uncaught` | Deduplicate identical errors by `(error_name, error_message_sanitized, path)` within 60 s to avoid error storms. |
| `incident_validation_failed` / `incident_transition_rejected` | Deduplicate by `(reason, field/attempted_status, branch)` within 60 s: a single operator retrying must not compound into an alert-worthy storm. Emit one per distinct failure signature and count occurrences in `properties` if needed. |
| `incident_created` | Idempotent by `incident_id`; ignore duplicate emissions on client retry. |
| `incident_status_changed` | Emit only when `from_status != to_status` (the backend already no-ops equal states), so it cannot fire on a re-confirmed state. |

### 6.3 Risks and exclusions

**Exclusions (will NOT be captured):**

- Consumer personal data (final recipient name, address, phone) — last-mile domain, out of scope.
- Credentials: passwords, password hashes, reset tokens, full JWTs, `Authorization` headers.
- Raw IP addresses and precise geolocation.
- Carrier data and shipment-level tracking (different project).
- Full JS stack traces (only sanitized message + hash).

**Considered and discarded events (explored, then dropped):**

| Considered event | Why it was discarded |
|---|---|
| `incident_description_text` (full description in `properties`) | Free text can contain consumer PII (names, addresses, phone); no analytical decision needs it. `incident_created` logs `description_length` instead. |
| `incident_description_viewed` | No decision beyond `incident_status_change_opened`; would add noise. |
| `stock_level_polled` (periodic stock snapshot per SKU) | High volume/cost and fully derivable from inbound/outbound orders; the dashboard computes stock on read. |
| `inventory_page_refreshed` (every `refresh()` call) | Already covered by `page_view`; per-refresh emission is high-frequency noise. |
| `session_heartbeat` / `idle_tick` | Pure volume with no decision; session boundaries come from `session_started`/`session_expired`. |
| `ui_heatmap` / `mouse_move` / `keypress` | High cost and privacy-invasive; not tied to any decision in §4.7. |
| `login_attempt` (pre-result, including email) | Would carry the email — privacy; `login_failed`/`login_succeeded` cover the decision. |
| `carrier_assigned` / `recipient_contacted` | Belongs to the last-mile project, out of scope for the inventory system. |

**Risks:**

| Risk | Impact | Mitigation |
|---|---|---|
| High volume of `page_view` / `api_response_time` | Storage/ingest cost | Batching, dedupe, sampling under peak, 60 s aggregation. |
| Sensitive data leaking into `properties` | Privacy/compliance | Strict allowlists (`additionalProperties: false`), collector rejects unknown keys. |
| Events emitted but never consumed | Waste | Every event has an owner and a decision in §4.7. |
| Clock skew between LA and Zaragoza | Wrong ordering | All timestamps in UTC ISO-8601; envelope is source of truth. |
| Duplicate events on retries | Inflated metrics | `event_id` as idempotency key at the collector. |
| Schema drift across frontend/backend | Broken dashboards | Versioned `schema_version` per event, single source `event-schemas.json`. |
| Frontend telemetry blocked by ad blockers / offline | Under-counting | Treat frontend counts as directional; backend events are authoritative for inventory. |

## 7. Seed data (for local verification of the mandatory metrics)

Aligned with the business context and the existing `seed_inventory.py`:

- 8–10 SKUs across ≥2 clients and the 3 categories (fashion, electronics, cosmetics).
- 2 warehouses (`los_angeles`, `zaragoza`).
- 15–20 inbound orders and 15–20 outbound orders distributed across both warehouses.
- ≥2 cases that fire `stock_threshold_triggered`.
- ≥1 case of `inventory_discrepancy_detected`.

## 8. Validation checklist

- [ ] `docs/telemetry/telemetry-plan.md` and `docs/telemetry/event-schemas.json` exist.
- [ ] All 5 mandatory event types are present with their required `properties`.
- [ ] Every event is classified as `obligatorio` or `oportunidad identificada` (§4.7).
- [ ] Every `event_type` follows the `entity_action` naming convention.
- [ ] The incident flow (`/incidents`) is instrumented: form opened, created, validation failed, status flow opened, status changed, transition rejected (§4.8).
- [ ] Every event declares `source`, `processing`, `golden_rule` and an `allowlist`.
- [ ] `event-schemas.json` is valid JSON and parses.
- [ ] No event allowlist includes credentials, consumer PII, IPs or carrier data.
- [ ] High-frequency events (`page_view`, `api_response_time`) declare a throttle/aggregation strategy.
- [ ] Considered-and-discarded events are documented with a reason (§6.3).
