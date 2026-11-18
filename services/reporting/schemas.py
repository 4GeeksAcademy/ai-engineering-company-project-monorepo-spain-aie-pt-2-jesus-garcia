from datetime import date, datetime

from pydantic import BaseModel, Field


class WeeklyPerformanceEntry(BaseModel):
    warehouse: str
    client_id: str
    inbound_units_count: int
    outbound_orders_count: int
    stockout_events_count: int
    discrepancy_events_count: int
    discrepancy_rate: float


class WeeklyPerformanceResponse(BaseModel):
    week_start: date
    entries: list[WeeklyPerformanceEntry]
    frozen: bool = False
    stale: bool = False
    computed_at: datetime | None = None


class PipelineRunLatest(BaseModel):
    run_id: str
    status: str
    week_start: date | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    rows_extracted: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_written: int = 0
    quality_status: str | None = None
    error_message: str | None = None
    source_fingerprint: str | None = None
    instrumentation_since: date | None = None
    stale: bool = False


class PipelineRunTriggerRequest(BaseModel):
    week_start: date | None = None
    lookback_weeks: int | None = Field(default=None, ge=1, le=12)


class PipelineRunTriggerResponse(BaseModel):
    run_id: str
    flow_run_id: str | None = None
    status: str = "scheduled"


# --- Alerta de umbral de negocio: SLA de entrega por país -------------------


class SlaRecipient(BaseModel):
    name: str
    role: str


class DeliverySlaCountry(BaseModel):
    country: str
    warehouse: str
    on_time_pct: float | None = None
    total_shipments: int = 0
    on_time_shipments: int = 0
    breached: bool = False
    recipients: list[SlaRecipient] = Field(default_factory=list)


class DeliverySlaStatus(BaseModel):
    week_start: date
    threshold_pct: float = 90.0
    breached: bool = False
    countries: list[DeliverySlaCountry] = Field(default_factory=list)
    computed_at: datetime | None = None


class SlaAlert(BaseModel):
    alert_id: str
    metric: str
    country: str
    warehouse: str | None = None
    week_start: date
    threshold_pct: float
    on_time_pct: float | None = None
    total_shipments: int
    on_time_shipments: int
    breached: bool
    recipients: list[SlaRecipient] = Field(default_factory=list)
    detected_at: str | None = None


class SlaEvaluationResponse(BaseModel):
    status: DeliverySlaStatus
    published: list[SlaAlert] = Field(default_factory=list)
