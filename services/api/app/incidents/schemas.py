from pydantic import BaseModel


class AnalysisResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    by_status: dict[str, int]
    avg_satisfaction_cerrados: float | None
    invalid_reasons: dict[str, int]
