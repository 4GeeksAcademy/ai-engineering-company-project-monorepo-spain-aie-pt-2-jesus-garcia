import re
from datetime import datetime, timezone
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
