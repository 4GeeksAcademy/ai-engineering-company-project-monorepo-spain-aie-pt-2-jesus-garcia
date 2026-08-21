from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, field_validator


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
    "in_progress": {"resolved", "discarded"},
    "resolved": set(),
    "discarded": set(),
}

FINAL_INCIDENT_STATUSES = {"resolved", "discarded"}


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


class IncidentCreate(BaseModel):
    title: str
    description: str
    origin: str
    branch: str
    category: str
    status: str = "open"

    @field_validator("origin")
    @classmethod
    def origin_must_be_valid(cls, v: str) -> str:
        if v not in INCIDENT_ORIGINS:
            raise ValueError(f"origin must be one of {INCIDENT_ORIGINS}")
        return v

    @field_validator("branch")
    @classmethod
    def branch_must_be_valid(cls, v: str) -> str:
        if v not in INCIDENT_BRANCHES:
            raise ValueError(f"branch must be one of {INCIDENT_BRANCHES}")
        return v

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: str) -> str:
        if v not in INCIDENT_CATEGORIES:
            raise ValueError(f"category must be one of {INCIDENT_CATEGORIES}")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in INCIDENT_STATUSES:
            raise ValueError(f"status must be one of {INCIDENT_STATUSES}")
        return v


class IncidentStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in INCIDENT_STATUSES:
            raise ValueError(f"status must be one of {INCIDENT_STATUSES}")
        return v
