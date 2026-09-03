from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator
import json


# --- CASE SCHEMAS ---
class CaseBase(BaseModel):
    case_id: str
    issue_type: str
    topology_note: Optional[str] = ""
    symptom: str
    show_outputs: str
    expected_fault: Optional[str] = ""
    osi_layer: Optional[str] = "Layer 3 (Network)"
    concept: Optional[str] = ""
    severity: Optional[str] = "Medium"
    expected_next_command: Optional[str] = ""
    expected_fix: Optional[str] = ""
    source_status: Optional[str] = "experiment"


class CaseCreate(CaseBase):
    pass


class CaseResponse(CaseBase):
    id: int
    created_at: str

    model_config = ConfigDict(from_attributes=True)


# --- RULE FINDING SCHEMAS ---
class RuleFindingBase(BaseModel):
    rule_name: str
    severity: str
    finding: str
    evidence: Optional[str] = ""
    recommendation: Optional[str] = ""


class RuleFindingCreate(RuleFindingBase):
    pass


class RuleFindingResponse(RuleFindingBase):
    id: int
    diagnosis_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# --- DIAGNOSIS SCHEMAS ---
class DiagnosisCreate(BaseModel):
    case_id: Optional[str] = None
    topology_note: Optional[str] = ""
    symptom: str
    show_outputs: str


class DiagnosisResponse(BaseModel):
    id: int
    case_id: Optional[str] = None
    topology_note: str
    symptom: str
    show_outputs: str
    probable_root_cause: str
    confidence_score: int
    confidence_label: str
    evidence_quotes: List[str]
    recommended_next_command: str
    suggested_fix: str
    safety_note: str
    source_status: str
    created_at: str
    rule_findings: List[RuleFindingResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_custom(cls, diagnosis_obj, rule_findings=None):
        raw_evidence = diagnosis_obj.evidence_quotes
        quotes = []
        if isinstance(raw_evidence, str):
            try:
                quotes = json.loads(raw_evidence)
            except Exception:
                quotes = [raw_evidence] if raw_evidence else []
        elif isinstance(raw_evidence, list):
            quotes = raw_evidence

        findings = []
        if rule_findings is not None:
            findings = [RuleFindingResponse.model_validate(rf) for rf in rule_findings]
        elif hasattr(diagnosis_obj, "rule_findings") and diagnosis_obj.rule_findings:
            findings = [RuleFindingResponse.model_validate(rf) for rf in diagnosis_obj.rule_findings]

        return cls(
            id=diagnosis_obj.id,
            case_id=diagnosis_obj.case_id,
            topology_note=diagnosis_obj.topology_note or "",
            symptom=diagnosis_obj.symptom or "",
            show_outputs=diagnosis_obj.show_outputs or "",
            probable_root_cause=diagnosis_obj.probable_root_cause or "",
            confidence_score=diagnosis_obj.confidence_score or 0,
            confidence_label=diagnosis_obj.confidence_label or "Medium",
            evidence_quotes=quotes,
            recommended_next_command=diagnosis_obj.recommended_next_command or "",
            suggested_fix=diagnosis_obj.suggested_fix or "",
            safety_note=diagnosis_obj.safety_note or "Human review is required before applying any fix.",
            source_status=diagnosis_obj.source_status or "sample",
            created_at=diagnosis_obj.created_at or "",
            rule_findings=findings
        )


# --- REVIEW SCHEMAS ---
class ReviewCreate(BaseModel):
    diagnosis_id: int
    decision: str = Field(..., description="Decision must be 'accepted', 'edited', or 'rejected'")
    reviewer_note: str = Field(..., description="Reviewer technical rationale notes are mandatory")
    corrected_root_cause: Optional[str] = None
    corrected_fix: Optional[str] = None
    verification_status: Optional[str] = Field(
        default="not_tested",
        description="Must be 'not_tested', 'fix_applied', 'verified', or 'failed_verification'"
    )
    reviewer_name: Optional[str] = "Alex Chen (Lead NetOps)"

    @model_validator(mode="after")
    def validate_decision_and_fields(self):
        decision_clean = self.decision.strip().lower()
        if decision_clean not in ["accepted", "edited", "rejected"]:
            raise ValueError("Decision must be 'accepted', 'edited', or 'rejected'")
        self.decision = decision_clean

        if not self.reviewer_note or not self.reviewer_note.strip():
            raise ValueError("Reviewer notes are mandatory to explain technical rationale.")
        self.reviewer_note = self.reviewer_note.strip()

        valid_verifications = ["not_tested", "fix_applied", "verified", "failed_verification"]
        v_clean = (self.verification_status or "not_tested").strip().lower()
        if v_clean not in valid_verifications:
            raise ValueError(f"Verification status must be one of {valid_verifications}")
        self.verification_status = v_clean

        if self.decision == "edited":
            if not self.corrected_fix or not self.corrected_fix.strip():
                raise ValueError("Corrected fix script is mandatory when decision is 'edited'")
            if not self.corrected_root_cause or not self.corrected_root_cause.strip():
                raise ValueError("Corrected root cause is mandatory when decision is 'edited'")
            self.corrected_fix = self.corrected_fix.strip()
            self.corrected_root_cause = self.corrected_root_cause.strip()

        return self


class ReviewResponse(BaseModel):
    id: int
    diagnosis_id: int
    decision: str
    reviewer_note: str
    corrected_root_cause: Optional[str] = None
    corrected_fix: Optional[str] = None
    verification_status: str
    reviewer_name: str
    reviewed_at: str

    model_config = ConfigDict(from_attributes=True)


# --- AUDIT EVENT SCHEMAS ---
class AuditEventResponse(BaseModel):
    id: int
    event_type: str
    case_id: Optional[str] = None
    diagnosis_id: Optional[int] = None
    review_id: Optional[int] = None
    details: Dict[str, Any]
    created_at: str


# --- DASHBOARD SUMMARY SCHEMAS ---
class DashboardSummary(BaseModel):
    total_cases: int
    pending_reviews: int
    verified_fixes: int
    human_agreement_rate: int
    accepted_count: int
    edited_count: int
    rejected_count: int
    human_ai_corrections_count: int
    issue_type_counts: Dict[str, int]
    severity_counts: Dict[str, int]
    osi_layer_counts: Dict[str, int]
    sample_cases_count: int
    experiment_cases_count: int
    recent_activity: List[Dict[str, Any]] = []


# --- CSV IMPORT SCHEMAS ---
class CSVImportError(BaseModel):
    row_number: int
    case_id: Optional[str] = None
    error: str


class CSVImportResult(BaseModel):
    imported_count: int
    failed_count: int
    errors: List[CSVImportError] = []
    cases: List[CaseResponse] = []
