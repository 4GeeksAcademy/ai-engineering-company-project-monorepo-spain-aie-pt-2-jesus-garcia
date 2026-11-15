import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as ORMField, Relationship, SQLModel


class UserRole(StrEnum):
    admin = "admin"
    manager = "manager"
    user = "user"


class Profile(BaseModel):
    id: str
    user_id: str
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class User(BaseModel):
    id: str
    email: str
    is_active: bool
    role: UserRole
    created_at: str


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str | None = None
    phone: str | None = None
    address: str | None = None

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email format")
        return v.lower().strip()


class UserUpdate(BaseModel):
    email: str | None = None
    role: UserRole | None = None

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email format")
        return v.lower().strip()


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email format")
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User


class AuthMeResponse(BaseModel):
    email: str
    role: UserRole
    profile: Profile


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str


VALID_CATEGORIES = [
    "carrier_last_mile",
    "carrier_international",
    "warehouse_supplies",
    "packaging_materials",
    "reverse_logistics",
    "fleet_maintenance",
    "it_and_wms_software",
    "cleaning_and_facilities",
]

VALID_STATUSES = ["active", "suspended"]
VALID_COUNTRIES = ["USA", "Spain"]
CURRENCY_BY_COUNTRY = {"USA": "USD", "Spain": "EUR"}


class Supplier(BaseModel):
    id: str
    name: str
    country: str
    categories: list[str] = Field(min_length=1)
    rate_per_shipment: float = Field(gt=0)
    currency: str
    updated_at: str
    status: str
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class SupplierListItem(BaseModel):
    id: str
    name: str
    country: str
    categories: list[str]
    rate_per_shipment: float
    currency: str
    status: str
    contact_email: str | None = None


class SupplierCreate(BaseModel):
    name: str
    country: str
    categories: list[str] = Field(min_length=1)
    rate_per_shipment: float = Field(gt=0)
    status: str = "active"
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    @field_validator("country")
    @classmethod
    def country_must_be_valid(cls, v: str) -> str:
        if v not in VALID_COUNTRIES:
            raise ValueError(f"country must be one of {VALID_COUNTRIES}")
        return v

    @field_validator("categories")
    @classmethod
    def categories_must_be_valid(cls, v: list[str]) -> list[str]:
        for cat in v:
            if cat not in VALID_CATEGORIES:
                raise ValueError(f"category '{cat}' not in {VALID_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @property
    def currency(self) -> str:
        return CURRENCY_BY_COUNTRY[self.country]


class SupplierUpdate(BaseModel):
    name: str | None = None
    categories: list[str] | None = None
    rate_per_shipment: float | None = Field(default=None, gt=0)
    status: str | None = None
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    @field_validator("categories")
    @classmethod
    def categories_must_be_valid(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for cat in v:
            if cat not in VALID_CATEGORIES:
                raise ValueError(f"category '{cat}' not in {VALID_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v


INCIDENT_ORIGINS = ["customer", "branch", "internal"]

INCIDENT_BRANCHES = [
    "central",
    "la_warehouse",
    "la_office",
    "zaragoza_warehouse",
    "zaragoza_office",
]

INCIDENT_CATEGORIES = [
    "lost_parcel",
    "delivery_failure",
    "inventory_discrepancy",
    "carrier_issue",
    "returns_issue",
    "warehouse_incident",
    "system_failure",
    "client_complaint",
    "other",
]

INCIDENT_STATUSES = ["open", "in_progress", "resolved", "discarded"]

INCIDENT_STATUS_TRANSITIONS = {
    "open": {"in_progress", "discarded"},
    "in_progress": {"resolved", "discarded", "open"},
    "resolved": {"in_progress"},
    "discarded": set(),
}

FINAL_INCIDENT_STATUSES = {"discarded"}


class Incident(BaseModel):
    id: str
    title: str
    description: str
    origin: str
    branch: str
    category: str
    status: str
    created_at: str
    updated_at: str


class IncidentListItem(BaseModel):
    id: str
    title: str
    description_excerpt: str
    origin: str
    branch: str
    category: str
    status: str


class IncidentCreate(BaseModel):
    title: str
    description: str
    origin: str
    branch: str
    category: str
    status: str = "open"


class IncidentStatusUpdate(BaseModel):
    status: str


class IncidentSummary(BaseModel):
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_origin: dict[str, int]
    by_branch: dict[str, int]


TELEMETRY_SCHEMA_VERSION = "2.0.0"
TELEMETRY_SCHEMA_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"


class TelemetrySource(StrEnum):
    frontend = "frontend"
    backend = "backend"


class TelemetryApp(StrEnum):
    backoffice = "backoffice"
    website = "website"


class TelemetryWarehouse(StrEnum):
    los_angeles = "los_angeles"
    zaragoza = "zaragoza"


class TelemetryEventType(StrEnum):
    inbound_order_created = "inbound_order_created"
    outbound_order_created = "outbound_order_created"
    stock_threshold_triggered = "stock_threshold_triggered"
    direct_stock_edit_rejected = "direct_stock_edit_rejected"
    inventory_discrepancy_detected = "inventory_discrepancy_detected"
    session_started = "session_started"
    login_succeeded = "login_succeeded"
    login_failed = "login_failed"
    session_expired = "session_expired"
    page_view = "page_view"
    pages_visited_in_session = "pages_visited_in_session"
    order_form_opened = "order_form_opened"
    order_form_abandoned = "order_form_abandoned"
    stock_validation_failed = "stock_validation_failed"
    outbound_rejected_insufficient_stock = "outbound_rejected_insufficient_stock"
    incident_form_opened = "incident_form_opened"
    incident_created = "incident_created"
    incident_validation_failed = "incident_validation_failed"
    incident_status_change_opened = "incident_status_change_opened"
    incident_status_changed = "incident_status_changed"
    incident_transition_rejected = "incident_transition_rejected"
    api_response_time = "api_response_time"
    frontend_error_uncaught = "frontend_error_uncaught"


class TelemetryEvent(BaseModel):
    event_id: str
    timestamp: str
    session_id: str
    user_id: str | None = None
    event_type: TelemetryEventType
    schema_version: str = TELEMETRY_SCHEMA_VERSION
    request_id: str | None = None
    source: TelemetrySource
    app: TelemetryApp
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def event_id_must_be_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except (ValueError, AttributeError, TypeError):
            raise ValueError("event_id must be a valid UUID")
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_iso8601(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValueError("timestamp must be an ISO-8601 string")
        return v

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("session_id must not be empty")
        return v

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_be_semver(cls, v: str) -> str:
        if not re.match(TELEMETRY_SCHEMA_VERSION_PATTERN, v):
            raise ValueError("schema_version must be semantic (x.y.z)")
        return v


class SKU(SQLModel, table=True):
    __tablename__ = "sku"
    id: int | None = ORMField(default=None, primary_key=True)
    name: str
    sku_code: str = ORMField(index=True)
    warehouse: str
    #: Cliente asignado. NULL = pendiente de mapeo (el pipeline lo cuarentena).
    client_id: str | None = ORMField(default=None)
    #: Umbral de stock. NULL = no configurado; 0 = umbral cero explícito.
    min_stock: int | None = ORMField(default=None)


class StockEntry(SQLModel, table=True):
    __tablename__ = "stock_entry"
    id: int | None = ORMField(default=None, primary_key=True)
    sku_id: int = ORMField(foreign_key="sku.id")
    quantity: int
    warehouse: str
    user_uuid: str
    client_id: str | None = ORMField(default=None)
    created_at: datetime = ORMField(default_factory=lambda: datetime.now(timezone.utc))
    product: SKU = Relationship()


class StockExit(SQLModel, table=True):
    __tablename__ = "stock_exit"
    id: int | None = ORMField(default=None, primary_key=True)
    sku_id: int = ORMField(foreign_key="sku.id")
    quantity: int
    warehouse: str
    user_uuid: str
    client_id: str | None = ORMField(default=None)
    created_at: datetime = ORMField(default_factory=lambda: datetime.now(timezone.utc))
    product: SKU = Relationship()


class InventoryDiscrepancy(SQLModel, table=True):
    """Detalle SQL de una discrepancia; el evento se emite una vez por pedido."""

    __tablename__ = "inventory_discrepancy"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "sku_id", name="uq_inventory_discrepancy_order_sku"
        ),
    )
    id: str = ORMField(default_factory=lambda: str(uuid4()), primary_key=True)
    order_id: str
    sku_id: int = ORMField(foreign_key="sku.id")
    warehouse: str
    client_id: str | None = ORMField(default=None)
    system_quantity: int
    physical_quantity: int
    discrepancy_delta: int
    incident_id: str | None = ORMField(default=None)
    created_at: datetime = ORMField(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryEventRecord(SQLModel, table=True):
    """Evento de telemetría persistido en `telemetry_events` (append-only).

    Las columnas fijas del envelope sostienen las consultas analíticas; la parte
    variable (`properties`) se guarda en `tags` (JSONB en PostgreSQL) filtrada
    previamente por el allowlist del catálogo.
    """

    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("ix_telemetry_events_timestamp", "timestamp"),
        Index("ix_telemetry_events_service", "service"),
        Index("ix_telemetry_events_session_id", "session_id"),
        Index("ix_telemetry_events_type_timestamp", "event_type", "timestamp"),
    )

    event_id: str = ORMField(sa_column=Column(Uuid(as_uuid=False), primary_key=True))
    timestamp: datetime = ORMField(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    received_at: datetime = ORMField(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )
    )
    event_type: str = ORMField(sa_column=Column(String(), nullable=False))
    service: str = ORMField(sa_column=Column(String(), nullable=False))
    session_id: str = ORMField(sa_column=Column(String(), nullable=False))
    user_id: str | None = ORMField(sa_column=Column(String(), nullable=True))
    schema_version: str = ORMField(sa_column=Column(String(), nullable=False))
    request_id: str | None = ORMField(sa_column=Column(String(), nullable=True))
    source: str = ORMField(sa_column=Column(String(), nullable=False))
    tags: dict = ORMField(
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        )
    )


class CustomerOrder(SQLModel, table=True):
    """Pedido mínimo para autorizar consultas de tracking por sesión.

    No sustituye al futuro servicio de tracking: solo guarda el propietario y
    el país del pedido, que son los dos datos que necesita el guard para
    rechazar accesos cruzados y para no mezclar políticas de país.
    """

    __tablename__ = "customer_order"
    id: int | None = ORMField(default=None, primary_key=True)
    order_ref: str = ORMField(index=True, unique=True, max_length=40)
    owner_user_id: str | None = ORMField(default=None, max_length=64)
    owner_email: str = ORMField(index=True, max_length=255)
    country: str = ORMField(max_length=2)
    carrier: str = ORMField(default="", max_length=40)
    status: str = ORMField(default="", max_length=40)
    delivered_at: datetime | None = ORMField(default=None)
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class DeadLetterTask(SQLModel, table=True):
    """Tarea que agotó sus reintentos y se conserva para diagnóstico.

    Es el registro durable de la Dead Letter Queue; la lista Redis
    ``dlq:trackflow`` es la vista operativa de la misma cola.
    """

    __tablename__ = "dead_letter_tasks"
    id: int | None = ORMField(default=None, primary_key=True)
    task_id: str = ORMField(index=True, unique=True)
    task_name: str
    attempts: int
    max_retries: int
    error_message: str
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# --- Recepción de RFPs (Hito 9, Parte 1) -------------------------------------

RFP_STATUS_ANALYZING = "analizando"
RFP_STATUS_COMPLETE = "analisis_completo"
RFP_STATUS_DISCARDED = "descartado"
RFP_STATUS_ERROR = "error"
# Hito 9, Parte 2 — generación y evaluación de secciones.
RFP_STATUS_DRAFTING = "generando_borrador"
RFP_STATUS_EVALUATING = "en_evaluación"
RFP_STATUS_NEEDS_REVIEW = "needs_human_review"
RFP_STATUS_AWAITING_APPROVAL = "esperando_aprobación"

RFP_SECTION_GENERATING = "generando"
RFP_SECTION_EVALUATING = "en_evaluación"
RFP_SECTION_PASSED = "evaluated_pass"
RFP_SECTION_NEEDS_REVIEW = "needs_human_review"

RFP_HANDOFF_NONE = "none"
RFP_HANDOFF_READY = "ready"


class RfpTicketStatus(StrEnum):
    analizando = RFP_STATUS_ANALYZING
    analisis_completo = RFP_STATUS_COMPLETE
    descartado = RFP_STATUS_DISCARDED
    error = RFP_STATUS_ERROR
    generando_borrador = RFP_STATUS_DRAFTING
    en_evaluación = RFP_STATUS_EVALUATING
    needs_human_review = RFP_STATUS_NEEDS_REVIEW
    esperando_aprobación = RFP_STATUS_AWAITING_APPROVAL


class RfpTicket(SQLModel, table=True):
    """Ticket de recepción de una RFP; fuente de verdad del estado del job."""

    __tablename__ = "rfp_ticket"
    __table_args__ = (
        Index("ix_rfp_ticket_status_created", "status", "created_at"),
    )

    id: str = ORMField(default_factory=lambda: str(uuid4()), primary_key=True)
    rfp_id: str = ORMField(index=True, unique=True, max_length=40)
    status: str = ORMField(default=RFP_STATUS_ANALYZING, index=True, max_length=40)
    pipeline_stage: str | None = ORMField(default=None, max_length=60)
    raw_pdf_path: str = ORMField(max_length=1024)
    markdown_path: str | None = ORMField(default=None, max_length=1024)
    original_filename: str = ORMField(max_length=255)
    file_sha256: str = ORMField(index=True, max_length=64)
    celery_task_id: str | None = ORMField(default=None, max_length=64)
    classification: dict | None = ORMField(
        default=None,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    discard_reason: str | None = ORMField(default=None, max_length=2000)
    error_message: str | None = ORMField(default=None, max_length=2000)
    handoff_status: str = ORMField(default=RFP_HANDOFF_NONE, max_length=20)
    handoff_payload: dict | None = ORMField(
        default=None,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    handoff_at: datetime | None = ORMField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    proposal_status: str | None = ORMField(default=None, max_length=40)
    proposal_stage: str | None = ORMField(default=None, max_length=60)
    proposal_payload: dict | None = ORMField(
        default=None,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    proposal_ready_at: datetime | None = ORMField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    proposal_task_id: str | None = ORMField(default=None, max_length=64)
    proposal_error: str | None = ORMField(default=None, max_length=2000)
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RfpMetadata(SQLModel, table=True):
    """Metadatos normalizados y métricas de legibilidad del documento."""

    __tablename__ = "rfp_metadata"

    id: int | None = ORMField(default=None, primary_key=True)
    ticket_id: str = ORMField(
        foreign_key="rfp_ticket.id", index=True, unique=True, max_length=36
    )
    client_name: str | None = ORMField(default=None, max_length=255)
    client_country: str | None = ORMField(default=None, max_length=20)
    currency: str | None = ORMField(default=None, max_length=3)
    language: str | None = ORMField(default=None, max_length=5)
    services_requested: list = ORMField(
        default_factory=list,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    departments_needed: list = ORMField(
        default_factory=list,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    monthly_volume: int | None = ORMField(default=None)
    deadline: date | None = ORMField(default=None)
    budget_range: str | None = ORMField(default=None, max_length=255)
    extraction: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    readability_metrics: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    document_metadata: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RfpDepartmentSection(SQLModel, table=True):
    """Aspectos clave y estado de aprobación por departamento.

    En la Parte 1 solo se rellenan ``key_aspects`` y ``open_questions``; los
    campos de borrador/evaluación/aprobación quedan preparados para las Partes
    2 y 3 sin migrar el modelo.
    """

    __tablename__ = "rfp_department_section"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "department_id",
            name="uq_rfp_department_section_ticket_department",
        ),
    )

    id: int | None = ORMField(default=None, primary_key=True)
    ticket_id: str = ORMField(
        foreign_key="rfp_ticket.id", index=True, max_length=36
    )
    department_id: str = ORMField(index=True, max_length=20)
    responsible: str | None = ORMField(default=None, max_length=120)
    key_aspects: list = ORMField(
        default_factory=list,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    open_questions: list = ORMField(
        default_factory=list,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    assumed_facts: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    unsupported_claims: list = ORMField(
        default_factory=list,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    draft_content: str | None = ORMField(default=None)
    evaluation_results: dict | None = ORMField(
        default=None,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    approval_status: str | None = ORMField(default=None, max_length=40)
    approver: str | None = ORMField(default=None, max_length=120)
    approved_at: datetime | None = ORMField(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Hito 9, Parte 2 — borrador y evaluación.
    draft_payload: dict | None = ORMField(
        default=None,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=True,
        ),
    )
    generation_status: str | None = ORMField(default=None, max_length=40)
    iteration_count: int = ORMField(default=0)
    needs_human_review: bool = ORMField(default=False)
    review_reason: str | None = ORMField(default=None)
    last_feedback: str | None = ORMField(default=None)
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RfpSectionEvaluation(SQLModel, table=True):
    """Histórico de cada iteración del ciclo generador-evaluador.

    ``rfp_department_section.evaluation_results`` guarda el último
    ``EvaluationResult``; esta tabla conserva la traza completa para auditar el
    ciclo y calcular las iteraciones medias por sección.
    """

    __tablename__ = "rfp_section_evaluation"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "department_id",
            "iteration",
            name="uq_rfp_section_evaluation_ticket_department_iteration",
        ),
        Index(
            "ix_rfp_section_evaluation_ticket",
            "ticket_id",
            "department_id",
        ),
    )

    id: int | None = ORMField(default=None, primary_key=True)
    ticket_id: str = ORMField(
        foreign_key="rfp_ticket.id", index=True, max_length=36
    )
    department_id: str = ORMField(index=True, max_length=20)
    iteration: int = ORMField(default=1)
    overall_pass: bool = ORMField(default=False)
    readability: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    relevance: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    compliance: dict = ORMField(
        default_factory=dict,
        sa_column=Column(
            JSON().with_variant(JSONB, "postgresql"),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    feedback: str | None = ORMField(default=None)
    created_at: datetime = ORMField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
