from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReportCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    marker: str
    evidence_id: UUID
    source_id: UUID
    section_key: str
    claim_text: str
    support_score: float
    status: str


class ResearchReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    title: str
    executive_summary: str
    recommendation: str
    confidence: float
    sections: list
    limitations: list
    markdown: str
    validation_status: str
    validation_score: float
    repair_attempts: int
    created_at: datetime
    updated_at: datetime


class CitationValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt: int
    valid: bool
    score: float
    issues: list
    created_at: datetime