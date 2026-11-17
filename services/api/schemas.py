from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    name: str
    sku_code: str
    warehouse: str
    client_id: str | None = None
    min_stock: int | None = Field(default=None, ge=0)


class SKURead(BaseModel):
    id: int
    name: str
    sku_code: str
    warehouse: str
    client_id: str | None = None
    min_stock: int | None = None
    current_stock: int = 0
    current_stock_by_warehouse: dict[str, int] = {}


class StockEntryCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    warehouse: str


class StockEntryRead(BaseModel):
    id: int
    sku_id: int
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime


class StockExitCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    warehouse: str


class StockExitRead(BaseModel):
    id: int
    sku_id: int
    quantity: int
    warehouse: str
    user_uuid: str
    created_at: datetime


class InventoryDiscrepancyCreate(BaseModel):
    order_id: str = Field(min_length=1)
    sku_id: int
    warehouse: str
    system_quantity: int = Field(ge=0)
    physical_quantity: int = Field(ge=0)
    incident_id: str | None = None


class InventoryDiscrepancyRead(BaseModel):
    id: str
    order_id: str
    sku_id: int
    warehouse: str
    client_id: str | None = None
    system_quantity: int
    physical_quantity: int
    discrepancy_delta: int
    incident_id: str | None = None
    created_at: datetime


class InventoryOrderItem(BaseModel):
    id: int
    order_type: str
    sku_id: int
    product_name: str
    warehouse: str
    quantity: int
    user_email: str = ""
    created_at: datetime


class TelemetryBatch(BaseModel):
    """Envelope laxo: los eventos se validan individualmente en el handler.

    El body completo solo falla si `events` no es una lista; así un evento
    inválido no tumba el resto del lote.
    """

    events: list[Any] = Field(default_factory=list)


class TelemetryIngestResponse(BaseModel):
    received: int
    stored: int
    rejected: int


class TelemetryPeriod(BaseModel):
    period_from: datetime = Field(alias="from")
    period_to: datetime = Field(alias="to")


class TelemetryReportResponse(BaseModel):
    period: TelemetryPeriod
    metrics: dict[str, list[dict[str, Any]]]

class AnalyzeTaskAccepted(BaseModel):
    """Respuesta 202 del análisis de incidencias encolado."""

    task_id: str


class TaskStatusResponse(BaseModel):
    """Estado de una tarea Celery consultado por el cliente."""

    task_id: str
    status: str
    result: Any = None


class RfpUploadResponse(BaseModel):
    """Respuesta rápida (202) de la subida de una RFP."""

    ticket_id: str
    rfp_id: str
    status: str
    task_id: str | None = None


class RfpTicketListItem(BaseModel):
    ticket_id: str
    rfp_id: str
    status: str
    pipeline_stage: str | None = None
    original_filename: str
    client_name: str | None = None
    client_country: str | None = None
    currency: str | None = None
    discard_reason: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RfpMetadataRead(BaseModel):
    client_name: str | None = None
    client_country: str | None = None
    currency: str | None = None
    language: str | None = None
    services_requested: list[str] = []
    departments_needed: list[str] = []
    monthly_volume: int | None = None
    deadline: str | None = None
    budget_range: str | None = None
    contact: dict = {}
    scope_notes: list[str] = []
    unknown_services: list[str] = []
    missing_fields: list[str] = []
    readability_metrics: dict = {}
    document_metadata: dict = {}


class RfpDepartmentSectionRead(BaseModel):
    department_id: str
    responsible: str | None = None
    key_aspects: list[dict] = []
    open_questions: list[str] = []
    assumed_facts: dict = {}
    unsupported_claims: list[dict] = []
    approval_status: str | None = None
    approver: str | None = None
    draft_content: str | None = None
    draft_payload: dict | None = None
    evaluation_results: dict | None = None
    generation_status: str | None = None
    iteration_count: int = 0
    needs_human_review: bool = False
    review_reason: str | None = None


class RfpTicketStatusRead(BaseModel):
    ticket_id: str
    rfp_id: str
    status: str
    pipeline_stage: str | None = None
    proposal_status: str | None = None
    approval_status: str | None = None
    discard_reason: str | None = None
    error_message: str | None = None
    handoff_status: str = "none"
    updated_at: datetime


class RfpProposalStartResponse(BaseModel):
    ticket_id: str
    task_id: str | None = None
    status: str


class RfpProposalSectionRead(BaseModel):
    section_id: str
    department_id: str
    department_label: str | None = None
    responsible: str | None = None
    status: str
    provisional: bool = False
    iteration_count: int = 0
    draft_content: str | None = None
    draft_payload: dict | None = None
    evaluation_results: dict | None = None
    review_reason: str | None = None
    approval_status: str | None = None
    approver: str | None = None


class RfpProposalRead(BaseModel):
    ticket_id: str
    rfp_id: str | None = None
    status: str
    generated_at: str | None = None
    client: dict = {}
    client_country: str | None = None
    currency: str | None = None
    services_requested: list[str] = []
    sections: list[RfpProposalSectionRead] = []
    needs_human_review_sections: list[str] = []
    metrics: dict = {}
    source_handoff: dict = {}


class RfpTicketRead(BaseModel):
    ticket_id: str
    rfp_id: str
    status: str
    pipeline_stage: str | None = None
    original_filename: str
    raw_pdf_path: str
    markdown_path: str | None = None
    file_sha256: str
    classification: dict | None = None
    discard_reason: str | None = None
    error_message: str | None = None
    handoff_status: str = "none"
    handoff: dict | None = None
    proposal_status: str | None = None
    proposal_error: str | None = None
    approval_status: str | None = None
    approval_thread_id: str | None = None
    approval_error: str | None = None
    final_document_ready: bool = False
    metadata: RfpMetadataRead | None = None
    sections: list[RfpDepartmentSectionRead] = []
    created_at: datetime
    updated_at: datetime


# --- Hito 9, Parte 3 — aprobación humana y cierre ---------------------------


class RfpApprovalDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "request_changes"]
    approver: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=4000)
    interrupt_id: str = Field(min_length=1, max_length=64)
    acknowledge_provisional: bool = False


class RfpApprovalPacketRead(BaseModel):
    department_id: str
    department_label: str | None = None
    responsible: str | None = None
    approval_status: str | None = None
    approval_round: int = 0
    interrupt_id: str | None = None
    provisional: bool = False
    packet: dict = {}


class RfpApprovalSummaryRead(BaseModel):
    department_id: str
    department_label: str | None = None
    responsible: str | None = None
    approval_status: str | None = None
    approver: str | None = None
    approved_at: str | None = None
    comment: str | None = None
    provisional: bool = False
    approval_round: int = 0


class RfpApprovalsRead(BaseModel):
    ticket_id: str
    rfp_id: str | None = None
    status: str
    approval_status: str | None = None
    thread_id: str | None = None
    run: int = 0
    max_rounds: int = 2
    pending: list[RfpApprovalPacketRead] = []
    decisions: list[RfpApprovalSummaryRead] = []
    final_document_ready: bool = False


class RfpApprovalResumeResponse(BaseModel):
    ticket_id: str
    task_id: str | None = None
    department_id: str
    action: str
    status: str
    pending_remaining: int = 0


class RfpApprovalStartResponse(BaseModel):
    ticket_id: str
    task_id: str | None = None
    status: str


class RfpFinalDocumentRead(BaseModel):
    contract_version: str = "rfp-final-v1"
    ticket_id: str
    currency: str | None = None
    sections: list[dict] = []
    approved_by: list[dict] = []
    markdown: str = ""
    document_path: str | None = None
    generated_at: str | None = None


class RfpTraceEventRead(BaseModel):
    event_id: str
    part: int
    sequence: int
    node: str
    agent: str | None = None
    department_id: str | None = None
    thread_id: str | None = None
    input: dict = {}
    output: dict = {}
    timestamp: str | None = None
    duration_ms: int | None = None


class RfpArbitrationRead(BaseModel):
    round: int
    trigger_id: str
    arbitrator: str | None = None
    rule: str | None = None
    affected_sections: list[str] = []
    resolution: dict = {}
    resolved: bool = False
    created_at: str | None = None


class RfpTraceRead(BaseModel):
    ticket_id: str
    events: list[RfpTraceEventRead] = []
    arbitrations: list[RfpArbitrationRead] = []
