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
