from models import TelemetryEventType

MANDATORY_EVENTS = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "direct_stock_edit_rejected",
    "inventory_discrepancy_detected",
)

HIGH_FREQUENCY_EVENTS = frozenset({"page_view", "api_response_time"})

CONSENT_REQUIRED_EVENTS = frozenset(
    {
        "session_started",
        "login_succeeded",
        "page_view",
        "pages_visited_in_session",
        "order_form_opened",
        "order_form_abandoned",
        "incident_form_opened",
        "incident_status_change_opened",
    }
)

EVENT_METADATA: dict[str, dict] = {
    "inbound_order_created": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["warehouse", "client_id", "product_id", "product_category", "quantity"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "quantity", "order_id", "available_after"],
    },
    "outbound_order_created": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["warehouse", "client_id", "product_id", "product_category", "quantity"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "quantity", "order_id", "available_after"],
    },
    "stock_threshold_triggered": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["warehouse", "client_id", "product_id", "product_category", "quantity", "min_stock"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "quantity", "min_stock", "deficit"],
    },
    "direct_stock_edit_rejected": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["rejection_reason", "endpoint"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "attempted_quantity", "rejection_reason", "endpoint", "user_role"],
    },
    "inventory_discrepancy_detected": {
        "source": "backend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["warehouse", "client_id", "product_id", "product_category", "quantity", "order_id"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "quantity", "order_id", "system_quantity", "physical_quantity", "discrepancy_delta", "detection_source", "incident_id"],
    },
    "session_started": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["user_role"],
        "allowlist": ["user_role", "entry_path"],
    },
    "login_succeeded": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["user_role", "method"],
        "allowlist": ["user_role", "method"],
    },
    "login_failed": {
        "source": "frontend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["failure_reason"],
        "allowlist": ["failure_reason", "method"],
    },
    "session_expired": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["reason"],
        "allowlist": ["reason", "last_path", "session_duration_seconds"],
    },
    "page_view": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": True,
        "required_properties": ["path", "app"],
        "allowlist": ["path", "referrer_path", "app", "dwell_time_ms"],
    },
    "pages_visited_in_session": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["page_count"],
        "allowlist": ["page_count", "unique_page_count", "top_path", "session_duration_seconds"],
    },
    "order_form_opened": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["warehouse", "order_type", "product_id"],
        "allowlist": ["warehouse", "order_type", "product_id", "product_category", "client_id"],
    },
    "order_form_abandoned": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["warehouse", "order_type", "product_id", "abandon_reason"],
        "allowlist": ["warehouse", "order_type", "product_id", "product_category", "client_id", "last_field_touched", "time_in_form_ms", "abandon_reason"],
    },
    "stock_validation_failed": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["field", "reason", "order_type"],
        "allowlist": ["warehouse", "product_id", "client_id", "product_category", "field", "reason", "attempted_quantity", "order_type"],
    },
    "outbound_rejected_insufficient_stock": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["warehouse", "client_id", "product_id", "product_category", "requested_quantity", "available_quantity"],
        "allowlist": ["warehouse", "client_id", "product_id", "product_category", "requested_quantity", "available_quantity", "deficit"],
    },
    "incident_form_opened": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": [],
        "allowlist": ["entry_source"],
    },
    "incident_created": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["incident_id", "category", "branch", "origin", "status"],
        "allowlist": ["incident_id", "category", "branch", "origin", "status", "description_length"],
    },
    "incident_validation_failed": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["field", "reason"],
        "allowlist": ["field", "reason", "origin", "branch", "category"],
    },
    "incident_status_change_opened": {
        "source": "frontend",
        "processing": "batch",
        "high_frequency": False,
        "required_properties": ["from_status"],
        "allowlist": ["incident_id", "from_status", "allowed_targets", "category", "branch"],
    },
    "incident_status_changed": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["incident_id", "from_status", "to_status", "category", "branch"],
        "allowlist": ["incident_id", "from_status", "to_status", "category", "branch", "time_in_status_seconds"],
    },
    "incident_transition_rejected": {
        "source": "backend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["incident_id", "from_status", "attempted_status", "reason"],
        "allowlist": ["incident_id", "from_status", "attempted_status", "reason", "category", "branch"],
    },
    "api_response_time": {
        "source": "backend",
        "processing": "batch",
        "high_frequency": True,
        "required_properties": ["method", "path", "status_code", "duration_ms"],
        "allowlist": ["method", "path", "status_code", "duration_ms", "app", "cache_hit"],
    },
    "frontend_error_uncaught": {
        "source": "frontend",
        "processing": "stream",
        "high_frequency": False,
        "required_properties": ["error_type", "error_name", "path"],
        "allowlist": ["error_type", "error_name", "error_message_sanitized", "path", "app"],
    },
}

KNOWN_EVENT_TYPES = frozenset(event.value for event in TelemetryEventType)


def get_event_metadata(event_type: str) -> dict | None:
    return EVENT_METADATA.get(event_type)


def get_allowlist(event_type: str) -> list[str]:
    metadata = EVENT_METADATA.get(event_type)
    return metadata["allowlist"] if metadata else []


def requires_consent(event_type: str) -> bool:
    return event_type in CONSENT_REQUIRED_EVENTS


def is_high_frequency(event_type: str) -> bool:
    return event_type in HIGH_FREQUENCY_EVENTS
