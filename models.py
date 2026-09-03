from datetime import datetime, timezone
import json
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from database import Base


def get_current_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(64), unique=True, index=True, nullable=False)
    issue_type = Column(String(64), index=True, nullable=False)
    topology_note = Column(Text, default="")
    symptom = Column(Text, nullable=False)
    show_outputs = Column(Text, nullable=False)
    expected_fault = Column(Text, default="")
    osi_layer = Column(String(64), default="Layer 3 (Network)")
    concept = Column(String(128), default="")
    severity = Column(String(32), default="Medium")
    expected_next_command = Column(String(256), default="")
    expected_fix = Column(Text, default="")
    source_status = Column(String(32), default="experiment", index=True)  # 'sample' or 'experiment'
    created_at = Column(String(64), default=get_current_time_iso)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(64), nullable=True, index=True)
    topology_note = Column(Text, default="")
    symptom = Column(Text, nullable=False)
    show_outputs = Column(Text, nullable=False)
    probable_root_cause = Column(Text, nullable=False)
    confidence_score = Column(Integer, default=75)
    confidence_label = Column(String(32), default="Medium")
    evidence_quotes = Column(Text, default="[]")  # JSON-encoded array of strings
    recommended_next_command = Column(String(256), default="")
    suggested_fix = Column(Text, default="")
    safety_note = Column(
        String(256),
        default="Human review is required before applying any fix."
    )
    source_status = Column(String(32), default="sample")  # 'sample' or 'experiment'
    created_at = Column(String(64), default=get_current_time_iso)

    rule_findings = relationship("RuleFinding", back_populates="diagnosis", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="diagnosis", cascade="all, delete-orphan")


class RuleFinding(Base):
    __tablename__ = "rule_findings"

    id = Column(Integer, primary_key=True, index=True)
    diagnosis_id = Column(Integer, ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=True, index=True)
    rule_name = Column(String(128), nullable=False)
    severity = Column(String(32), default="warning")  # 'critical', 'error', 'warning', 'info'
    finding = Column(Text, nullable=False)
    evidence = Column(Text, default="")
    recommendation = Column(Text, default="")

    diagnosis = relationship("Diagnosis", back_populates="rule_findings")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    diagnosis_id = Column(Integer, ForeignKey("diagnoses.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(32), nullable=False)  # 'accepted', 'edited', 'rejected'
    reviewer_note = Column(Text, nullable=False)
    corrected_root_cause = Column(Text, nullable=True)
    corrected_fix = Column(Text, nullable=True)
    verification_status = Column(String(64), default="not_tested")  # 'not_tested', 'fix_applied', 'verified', 'failed_verification'
    reviewer_name = Column(String(128), default="Alex Chen (Lead NetOps)")
    reviewed_at = Column(String(64), default=get_current_time_iso)

    diagnosis = relationship("Diagnosis", back_populates="reviews")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(64), index=True, nullable=False)
    case_id = Column(String(64), nullable=True, index=True)
    diagnosis_id = Column(Integer, nullable=True, index=True)
    review_id = Column(Integer, nullable=True, index=True)
    details = Column(Text, default="{}")  # JSON or text description
    created_at = Column(String(64), default=get_current_time_iso)
