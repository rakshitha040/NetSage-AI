import os
import io
import csv
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import engine, Base, get_db, SessionLocal
import models
import schemas
from rules import run_deterministic_rules
from ai_service import get_ai_provider

from contextlib import asynccontextmanager

def seed_db(force: bool = False):
    """Seed initial real cases from data/cases.csv and 5 Responsible AI audit incidents."""
    db = SessionLocal()
    try:
        case_count = db.query(models.Case).count()
        if case_count == 0 or force:
            if force:
                db.query(models.RuleFinding).delete()
                db.query(models.Review).delete()
                db.query(models.Diagnosis).delete()
                db.query(models.AuditEvent).delete()
                db.query(models.Case).delete()
                db.commit()

            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cases.csv")
            if os.path.exists(csv_path):
                with open(csv_path, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        case_obj = models.Case(
                            case_id=row.get("case_id", "").strip(),
                            issue_type=row.get("issue_type", "VLAN").strip(),
                            topology_note=row.get("topology_note", "").strip(),
                            symptom=row.get("symptom", "").strip(),
                            show_outputs=row.get("show_outputs", "").strip(),
                            expected_fault=row.get("expected_fault", "").strip(),
                            osi_layer=row.get("osi_layer", "Layer 3").strip(),
                            concept=row.get("concept", "").strip(),
                            severity=row.get("severity", "Medium").strip(),
                            expected_next_command=row.get("expected_next_command", "").strip(),
                            expected_fix=row.get("expected_fix", "").strip(),
                            source_status="sample",
                            created_at=get_iso_timestamp()
                        )
                        db.add(case_obj)
                db.commit()

            # Seed 5 Documented Responsible AI Incidents
            responsible_ai_seeds = [
                {
                    "case_id": "CASE-01",
                    "symptom": "PC1 (VLAN5) cannot communicate with Server1 (VLAN10) via router R1.",
                    "show_outputs": "SW1#show interfaces gigabitEthernet 0/1 switchport\nAdministrative Mode: static access\nOperational Mode: static access",
                    "ai_root": "VLAN 5 and 10 need to be recreated on the switch.",
                    "ai_fix": "vlan 5\n name VLAN5\nvlan 10\n name VLAN10",
                    "decision": "edited",
                    "corrected_root": "SW1 uplink Gi0/1 is in access mode in VLAN 5 instead of 802.1Q trunking.",
                    "corrected_fix": "SW1(config)# interface gigabitEthernet 0/1\nSW1(config-if)# switchport mode trunk\nSW1(config-if)# end",
                    "note": "AI hallucinated VLAN recreation. Human engineer caught that Gi0/1 was in access mode and configured trunking.",
                    "reviewer": "Alex Chen (Lead NetOps)"
                },
                {
                    "case_id": "CASE-05",
                    "symptom": "PC1 cannot reach remote network (172.16.2.1); no NAT translations created.",
                    "show_outputs": "R1#show access-lists 1\nStandard IP access list 1\n 10 permit 192.168.2.0, wildcard bits 0.0.0.255",
                    "ai_root": "NAT pool IP range is exhausted or invalid.",
                    "ai_fix": "no ip nat pool NATPOOL\nip nat pool NATPOOL 172.16.1.100 172.16.1.200 netmask 255.255.255.0",
                    "decision": "edited",
                    "corrected_root": "Standard ACL 1 permits wrong subnet (192.168.2.0/24 instead of 192.168.1.0/24).",
                    "corrected_fix": "R1(config)# access-list 1 permit 192.168.1.0 0.0.0.255\nR1(config)# no access-list 1 permit 192.168.2.0 0.0.0.255",
                    "note": "AI proposed rebuilding the NAT pool. Human engineer identified the exact defect in ACL 1 source subnet matching.",
                    "reviewer": "Alex Chen (Lead NetOps)"
                },
                {
                    "case_id": "CASE-08",
                    "symptom": "PC1 cannot reach 172.16.2.1; no NAT translations occur.",
                    "show_outputs": "R1#show running-config | section nat\nip nat pool NATPOOL 172.16.1.50 172.16.1.60 netmask 255.255.255.0",
                    "ai_root": "Interfaces Fa0/0 and Fa0/1 missing IP NAT inside/outside assignment.",
                    "ai_fix": "interface Fa0/0\n ip nat inside\ninterface Fa0/1\n ip nat outside",
                    "decision": "edited",
                    "corrected_root": "Global NAT binding command 'ip nat inside source list 1 pool NATPOOL overload' is missing.",
                    "corrected_fix": "R1(config)# ip nat inside source list 1 pool NATPOOL overload",
                    "note": "Interfaces already had inside/outside configured. Human caught the missing overload binding rule.",
                    "reviewer": "Alex Chen (Lead NetOps)"
                },
                {
                    "case_id": "CASE-21",
                    "symptom": "Both PC1 and PC2 cannot reach remote PC3 (172.16.3.10) after applying ACL 120.",
                    "show_outputs": "Extended IP access list 120\n 10 deny icmp host 192.168.1.11 host 172.16.3.10 (4 match(es))",
                    "ai_root": "ACL 120 is blocking all ICMP traffic; recommend removing access-group 120 from Fa0/0.",
                    "ai_fix": "interface FastEthernet0/0\n no ip access-group 120 in",
                    "decision": "edited",
                    "corrected_root": "ACL 120 lacks trailing permit rule; implicit deny blocks all remaining traffic.",
                    "corrected_fix": "R1(config)# ip access-list extended 120\nR1(config-ext-nacl)# permit ip any any\nR1(config-ext-nacl)# end",
                    "note": "Removing ACL would violate security intent. Human engineer appended permit ip any any to satisfy implicit deny.",
                    "reviewer": "Alex Chen (Lead NetOps)"
                },
                {
                    "case_id": "CASE-22",
                    "symptom": "PC2 cannot reach remote PC3 (172.16.3.10) due to static routing failure.",
                    "show_outputs": "R1#show ip route\nS 172.16.3.0/24 [1/0] via 172.16.2.254",
                    "ai_root": "Static routing insufficient; configure OSPF dynamic routing across R1 and R2.",
                    "ai_fix": "router ospf 1\n network 172.16.2.0 0.0.0.255 area 0",
                    "decision": "edited",
                    "corrected_root": "Static route next-hop is set to unreachable IP 172.16.2.254 instead of R2 at 172.16.2.1.",
                    "corrected_fix": "R1(config)# no ip route 172.16.3.0 255.255.255.0 172.16.2.254\nR1(config)# ip route 172.16.3.0 255.255.255.0 172.16.2.1",
                    "note": "Prevented AI architecture drift (introducing OSPF into static lab). Corrected static route next-hop to 172.16.2.1.",
                    "reviewer": "Alex Chen (Lead NetOps)"
                }
            ]

            for seed in responsible_ai_seeds:
                diag = models.Diagnosis(
                    case_id=seed["case_id"],
                    topology_note="",
                    symptom=seed["symptom"],
                    show_outputs=seed["show_outputs"],
                    probable_root_cause=seed["ai_root"],
                    confidence_score=85,
                    confidence_label="Medium",
                    evidence_quotes=json.dumps([seed["show_outputs"].splitlines()[0]]),
                    recommended_next_command="show running-config",
                    suggested_fix=seed["ai_fix"],
                    safety_note="Human review is required before applying any fix.",
                    source_status="sample",
                    created_at=get_iso_timestamp()
                )
                db.add(diag)
                db.flush()

                rev = models.Review(
                    diagnosis_id=diag.id,
                    decision=seed["decision"],
                    reviewer_note=seed["note"],
                    corrected_root_cause=seed["corrected_root"],
                    corrected_fix=seed["corrected_fix"],
                    verification_status="verified",
                    reviewer_name=seed["reviewer"],
                    reviewed_at=get_iso_timestamp()
                )
                db.add(rev)
                db.flush()

                db.add(models.AuditEvent(
                    event_type="REVIEW_SUBMITTED",
                    case_id=seed["case_id"],
                    diagnosis_id=diag.id,
                    review_id=rev.id,
                    details=json.dumps({
                        "decision": seed["decision"],
                        "verification_status": "verified",
                        "reviewer": seed["reviewer"],
                        "reviewer_note": seed["note"],
                        "is_ai_correction": True,
                        "ai_root_cause": seed["ai_root"],
                        "final_fix": seed["corrected_fix"]
                    }),
                    created_at=get_iso_timestamp()
                ))

            db.add(models.AuditEvent(
                event_type="SYSTEM_INITIALIZED",
                case_id=None,
                details=json.dumps({"message": "NetSage AI initialized with 30 real lab cases and 5 Responsible AI audit records", "status": "sample"}),
                created_at=get_iso_timestamp()
            ))
            db.commit()
    except Exception as e:
        print(f"Error during startup seeding: {e}")
        db.rollback()
    finally:
        db.close()


Base.metadata.create_all(bind=engine)

def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_db()
    yield

app = FastAPI(
    title="NetSage AI - Cisco Packet Tracer Troubleshooting Assistant",
    description="AI-assisted Cisco network troubleshooting system with deterministic rule checking and mandatory human review.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- HEALTH CHECK ---
@app.get("/api/health")
def get_health():
    return {
        "status": "healthy",
        "service": "NetSage AI",
        "version": "1.0.0",
        "timestamp": get_iso_timestamp()
    }


# --- DASHBOARD SUMMARY ---
@app.get("/api/dashboard/summary", response_model=schemas.DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    cases = db.query(models.Case).all()
    diagnoses = db.query(models.Diagnosis).all()
    reviews = db.query(models.Review).all()

    total_cases = len(cases)
    sample_cases_count = sum(1 for c in cases if c.source_status == "sample")
    experiment_cases_count = sum(1 for c in cases if c.source_status == "experiment")

    reviewed_diag_ids = {r.diagnosis_id for r in reviews}
    pending_reviews = sum(1 for d in diagnoses if d.id not in reviewed_diag_ids)

    verified_fixes = sum(1 for r in reviews if r.verification_status == "verified")
    accepted_count = sum(1 for r in reviews if r.decision == "accepted")
    edited_count = sum(1 for r in reviews if r.decision == "edited")
    rejected_count = sum(1 for r in reviews if r.decision == "rejected")
    human_ai_corrections_count = edited_count + rejected_count

    total_decisions = accepted_count + edited_count + rejected_count
    human_agreement_rate = round((accepted_count / total_decisions) * 100) if total_decisions > 0 else 100

    issue_type_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {"High": 0, "Medium": 0, "Low": 0}
    osi_layer_counts: Dict[str, int] = {}

    for c in cases:
        issue_type_counts[c.issue_type] = issue_type_counts.get(c.issue_type, 0) + 1
        sev = c.severity.capitalize() if c.severity else "Medium"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        osi = c.osi_layer or "Layer 3 (Network)"
        osi_layer_counts[osi] = osi_layer_counts.get(osi, 0) + 1

    # Recent activity
    recent_events = db.query(models.AuditEvent).order_by(desc(models.AuditEvent.id)).limit(10).all()
    activity_list = []
    for ev in recent_events:
        try:
            det = json.loads(ev.details) if ev.details else {}
        except Exception:
            det = {"raw": ev.details}
        activity_list.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "case_id": ev.case_id or det.get("case_id", "N/A"),
            "diagnosis_id": ev.diagnosis_id,
            "review_id": ev.review_id,
            "details": det,
            "created_at": ev.created_at
        })

    return schemas.DashboardSummary(
        total_cases=total_cases,
        pending_reviews=pending_reviews,
        verified_fixes=verified_fixes,
        human_agreement_rate=human_agreement_rate,
        accepted_count=accepted_count,
        edited_count=edited_count,
        rejected_count=rejected_count,
        human_ai_corrections_count=human_ai_corrections_count,
        issue_type_counts=issue_type_counts,
        severity_counts=severity_counts,
        osi_layer_counts=osi_layer_counts,
        sample_cases_count=sample_cases_count,
        experiment_cases_count=experiment_cases_count,
        recent_activity=activity_list
    )


# --- CASES API ---
@app.get("/api/cases", response_model=List[schemas.CaseResponse])
def get_cases(
    issue_type: Optional[str] = None,
    severity: Optional[str] = None,
    source_status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Case)
    if issue_type and issue_type != "ALL":
        query = query.filter(models.Case.issue_type == issue_type)
    if severity and severity != "ALL":
        query = query.filter(models.Case.severity == severity)
    if source_status and source_status != "ALL":
        query = query.filter(models.Case.source_status == source_status)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (models.Case.case_id.ilike(search_pattern)) |
            (models.Case.symptom.ilike(search_pattern)) |
            (models.Case.concept.ilike(search_pattern)) |
            (models.Case.topology_note.ilike(search_pattern))
        )
    return query.order_by(models.Case.id.asc()).all()


@app.get("/api/cases/{case_id}", response_model=schemas.CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case_obj = db.query(models.Case).filter(models.Case.case_id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail=f"Case with ID '{case_id}' not found.")
    return case_obj


# --- CSV IMPORT ---
REQUIRED_CSV_HEADERS = [
    "case_id", "issue_type", "topology_note", "symptom", "show_outputs",
    "expected_fault", "osi_layer", "concept", "severity",
    "expected_next_command", "expected_fix"
]

@app.post("/api/cases/import-csv", response_model=schemas.CSVImportResult)
async def import_cases_csv(
    file: Optional[UploadFile] = File(None),
    raw_csv: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    csv_content = ""
    if file:
        content_bytes = await file.read()
        try:
            csv_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            csv_content = content_bytes.decode("latin-1")
    elif raw_csv:
        csv_content = raw_csv
    else:
        raise HTTPException(
            status_code=400,
            detail="No CSV file or raw_csv string provided."
        )

    f = io.StringIO(csv_content.strip())
    reader = csv.reader(f)
    try:
        headers = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    clean_headers = [h.strip() for h in headers]
    missing_headers = [req for req in REQUIRED_CSV_HEADERS if req not in clean_headers]
    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required headers: {', '.join(missing_headers)}. Required headers: {', '.join(REQUIRED_CSV_HEADERS)}"
        )

    header_index = {h: i for i, h in enumerate(clean_headers)}
    imported_cases: List[models.Case] = []
    errors: List[schemas.CSVImportError] = []

    row_num = 1  # 1-indexed (header is row 1)
    for row in reader:
        row_num += 1
        if not row or not any(field.strip() for field in row):
            continue

        try:
            case_id = row[header_index["case_id"]].strip() if len(row) > header_index["case_id"] else ""
            if not case_id:
                errors.append(schemas.CSVImportError(row_number=row_num, error="Missing required 'case_id'"))
                continue

            issue_type = row[header_index["issue_type"]].strip() if len(row) > header_index["issue_type"] else "VLAN"
            symptom = row[header_index["symptom"]].strip() if len(row) > header_index["symptom"] else ""
            show_outputs = row[header_index["show_outputs"]].strip() if len(row) > header_index["show_outputs"] else ""

            if not symptom:
                errors.append(schemas.CSVImportError(row_number=row_num, case_id=case_id, error="Missing required 'symptom' field"))
                continue
            if not show_outputs:
                errors.append(schemas.CSVImportError(row_number=row_num, case_id=case_id, error="Missing required 'show_outputs' field"))
                continue

            topology_note = row[header_index["topology_note"]].strip() if len(row) > header_index["topology_note"] else ""
            expected_fault = row[header_index["expected_fault"]].strip() if len(row) > header_index["expected_fault"] else ""
            osi_layer = row[header_index["osi_layer"]].strip() if len(row) > header_index["osi_layer"] else "Layer 3 (Network)"
            concept = row[header_index["concept"]].strip() if len(row) > header_index["concept"] else ""
            severity = row[header_index["severity"]].strip() if len(row) > header_index["severity"] else "Medium"
            expected_next_command = row[header_index["expected_next_command"]].strip() if len(row) > header_index["expected_next_command"] else ""
            expected_fix = row[header_index["expected_fix"]].strip() if len(row) > header_index["expected_fix"] else ""

            # Check if case exists, if so update; else create new
            existing = db.query(models.Case).filter(models.Case.case_id == case_id).first()
            if existing:
                existing.issue_type = issue_type
                existing.topology_note = topology_note
                existing.symptom = symptom
                existing.show_outputs = show_outputs
                existing.expected_fault = expected_fault
                existing.osi_layer = osi_layer
                existing.concept = concept
                existing.severity = severity
                existing.expected_next_command = expected_next_command
                existing.expected_fix = expected_fix
                existing.source_status = "experiment"
                case_obj = existing
            else:
                case_obj = models.Case(
                    case_id=case_id,
                    issue_type=issue_type,
                    topology_note=topology_note,
                    symptom=symptom,
                    show_outputs=show_outputs,
                    expected_fault=expected_fault,
                    osi_layer=osi_layer,
                    concept=concept,
                    severity=severity,
                    expected_next_command=expected_next_command,
                    expected_fix=expected_fix,
                    source_status="experiment",
                    created_at=get_iso_timestamp()
                )
                db.add(case_obj)

            imported_cases.append(case_obj)
        except Exception as ex:
            errors.append(schemas.CSVImportError(row_number=row_num, error=str(ex)))

    db.commit()

    # Log audit event
    db.add(models.AuditEvent(
        event_type="CASE_IMPORTED",
        details=json.dumps({
            "imported_count": len(imported_cases),
            "failed_count": len(errors),
            "source_status": "experiment"
        }),
        created_at=get_iso_timestamp()
    ))
    db.commit()

    return schemas.CSVImportResult(
        imported_count=len(imported_cases),
        failed_count=len(errors),
        errors=errors,
        cases=[schemas.CaseResponse.model_validate(c) for c in imported_cases]
    )


# --- DIAGNOSES API ---
@app.post("/api/diagnoses", response_model=schemas.DiagnosisResponse)
def create_diagnosis(payload: schemas.DiagnosisCreate, db: Session = Depends(get_db)):
    # 1. Run deterministic rule checker
    rule_findings_data = run_deterministic_rules(
        show_outputs=payload.show_outputs,
        symptom=payload.symptom,
        topology_note=payload.topology_note or ""
    )

    # 2. Get AI recommendation from AI provider
    ai_provider = get_ai_provider()
    ai_result = ai_provider.diagnose(
        symptom=payload.symptom,
        show_outputs=payload.show_outputs,
        topology_note=payload.topology_note or "",
        rule_findings=rule_findings_data,
        case_id=payload.case_id
    )

    # 3. Determine source status
    source_status = "sample"
    if payload.case_id:
        c_obj = db.query(models.Case).filter(models.Case.case_id == payload.case_id).first()
        if c_obj:
            source_status = c_obj.source_status or "sample"

    # 4. Save Diagnosis to DB
    diag_obj = models.Diagnosis(
        case_id=payload.case_id,
        topology_note=payload.topology_note or "",
        symptom=payload.symptom,
        show_outputs=payload.show_outputs,
        probable_root_cause=ai_result["probable_root_cause"],
        confidence_score=ai_result["confidence_score"],
        confidence_label=ai_result["confidence_label"],
        evidence_quotes=json.dumps(ai_result["evidence_quotes"]),
        recommended_next_command=ai_result["recommended_next_command"],
        suggested_fix=ai_result["suggested_fix"],
        safety_note=ai_result["safety_note"],
        source_status=source_status,
        created_at=get_iso_timestamp()
    )
    db.add(diag_obj)
    db.flush()  # populate diag_obj.id

    # 5. Save RuleFindings to DB linked to diagnosis
    saved_findings = []
    for rf in rule_findings_data:
        rf_obj = models.RuleFinding(
            diagnosis_id=diag_obj.id,
            rule_name=rf.rule_name,
            severity=rf.severity,
            finding=rf.finding,
            evidence=rf.evidence or "",
            recommendation=rf.recommendation or ""
        )
        db.add(rf_obj)
        saved_findings.append(rf_obj)

    # 6. Record Audit Event
    audit_ev = models.AuditEvent(
        event_type="DIAGNOSIS_CREATED",
        case_id=payload.case_id,
        diagnosis_id=diag_obj.id,
        details=json.dumps({
            "confidence": f"{diag_obj.confidence_label} ({diag_obj.confidence_score}%)",
            "rule_findings_count": len(saved_findings),
            "safety_note": diag_obj.safety_note,
            "source_status": diag_obj.source_status
        }),
        created_at=get_iso_timestamp()
    )
    db.add(audit_ev)
    db.commit()
    db.refresh(diag_obj)

    return schemas.DiagnosisResponse.from_orm_custom(diag_obj, saved_findings)


@app.get("/api/diagnoses/{diagnosis_id}", response_model=schemas.DiagnosisResponse)
def get_diagnosis(diagnosis_id: int, db: Session = Depends(get_db)):
    diag_obj = db.query(models.Diagnosis).filter(models.Diagnosis.id == diagnosis_id).first()
    if not diag_obj:
        raise HTTPException(status_code=404, detail=f"Diagnosis #{diagnosis_id} not found.")
    return schemas.DiagnosisResponse.from_orm_custom(diag_obj)


# --- REVIEWS API ---
@app.get("/api/reviews/pending", response_model=List[schemas.DiagnosisResponse])
def get_pending_reviews(db: Session = Depends(get_db)):
    reviewed_ids = {r.diagnosis_id for r in db.query(models.Review.diagnosis_id).all()}
    pending_diagnoses = db.query(models.Diagnosis).filter(~models.Diagnosis.id.in_(reviewed_ids)).order_by(models.Diagnosis.id.desc()).all()
    return [schemas.DiagnosisResponse.from_orm_custom(d) for d in pending_diagnoses]


@app.post("/api/reviews", response_model=schemas.ReviewResponse)
def create_review(payload: schemas.ReviewCreate, db: Session = Depends(get_db)):
    diag_obj = db.query(models.Diagnosis).filter(models.Diagnosis.id == payload.diagnosis_id).first()
    if not diag_obj:
        raise HTTPException(status_code=404, detail=f"Diagnosis #{payload.diagnosis_id} does not exist.")

    # Save Review
    review_obj = models.Review(
        diagnosis_id=payload.diagnosis_id,
        decision=payload.decision,
        reviewer_note=payload.reviewer_note,
        corrected_root_cause=payload.corrected_root_cause,
        corrected_fix=payload.corrected_fix,
        verification_status=payload.verification_status,
        reviewer_name=payload.reviewer_name or "Alex Chen (Lead NetOps)",
        reviewed_at=get_iso_timestamp()
    )
    db.add(review_obj)
    db.flush()

    # Record Audit Event
    is_correction = payload.decision in ["edited", "rejected"]
    audit_ev = models.AuditEvent(
        event_type="REVIEW_SUBMITTED",
        case_id=diag_obj.case_id,
        diagnosis_id=diag_obj.id,
        review_id=review_obj.id,
        details=json.dumps({
            "decision": payload.decision,
            "verification_status": payload.verification_status,
            "reviewer": payload.reviewer_name,
            "reviewer_note": payload.reviewer_note,
            "is_ai_correction": is_correction,
            "ai_root_cause": diag_obj.probable_root_cause,
            "final_fix": payload.corrected_fix if payload.decision == "edited" else diag_obj.suggested_fix
        }),
        created_at=get_iso_timestamp()
    )
    db.add(audit_ev)
    db.commit()
    db.refresh(review_obj)

    return review_obj


# --- AUDIT LOG API ---
@app.get("/api/audit-log")
def get_audit_log(
    decision: Optional[str] = Query(None),
    only_corrections: Optional[bool] = Query(False),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    reviews = db.query(models.Review).order_by(desc(models.Review.id)).all()
    results = []

    for r in reviews:
        diag = r.diagnosis
        case_obj = None
        if diag and diag.case_id:
            case_obj = db.query(models.Case).filter(models.Case.case_id == diag.case_id).first()

        is_correction = r.decision in ["edited", "rejected"]

        if decision and decision != "ALL" and r.decision.lower() != decision.lower():
            continue
        if only_corrections and not is_correction:
            continue

        item = {
            "id": f"AUDIT-{r.id:04d}",
            "review_id": r.id,
            "diagnosis_id": r.diagnosis_id,
            "case_id": diag.case_id if diag else "CUSTOM-LAB",
            "case_title": case_obj.concept if case_obj and case_obj.concept else (diag.symptom[:50] if diag else "Custom Case"),
            "issue_type": case_obj.issue_type if case_obj else "Custom",
            "human_decision": r.decision.capitalize(),
            "verification_status": r.verification_status,
            "reviewer": r.reviewer_name,
            "reviewer_note": r.reviewer_note,
            "is_ai_correction": is_correction,
            "ai_root_cause": diag.probable_root_cause if diag else "",
            "ai_suggested_fix": diag.suggested_fix if diag else "",
            "corrected_root_cause": r.corrected_root_cause or "",
            "final_applied_fix": r.corrected_fix if r.decision == "edited" else (diag.suggested_fix if diag else ""),
            "timestamp": r.reviewed_at
        }

        if search:
            search_str = f"{item['case_id']} {item['case_title']} {item['reviewer']} {item['reviewer_note']}".lower()
            if search.lower() not in search_str:
                continue

        results.append(item)

    return results


# --- EXPORTS API ---
@app.get("/api/export/cases.csv")
def export_cases_csv(db: Session = Depends(get_db)):
    cases = db.query(models.Case).order_by(models.Case.id.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(REQUIRED_CSV_HEADERS)
    for c in cases:
        writer.writerow([
            c.case_id,
            c.issue_type,
            c.topology_note or "",
            c.symptom or "",
            c.show_outputs or "",
            c.expected_fault or "",
            c.osi_layer or "",
            c.concept or "",
            c.severity or "",
            c.expected_next_command or "",
            c.expected_fix or ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cases.csv"'}
    )


@app.get("/api/export/audit-report.csv")
def export_audit_report_csv(db: Session = Depends(get_db)):
    reviews = db.query(models.Review).order_by(desc(models.Review.id)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "audit_id", "case_id", "issue_type", "human_decision", "verification_status",
        "reviewer", "reviewer_note", "is_ai_correction", "ai_root_cause",
        "ai_suggested_fix", "final_approved_fix", "reviewed_at"
    ])

    for r in reviews:
        diag = r.diagnosis
        case_obj = db.query(models.Case).filter(models.Case.case_id == diag.case_id).first() if (diag and diag.case_id) else None
        is_correction = "YES" if r.decision in ["edited", "rejected"] else "NO"
        final_fix = r.corrected_fix if r.decision == "edited" else (diag.suggested_fix if diag else "")

        writer.writerow([
            f"AUDIT-{r.id:04d}",
            diag.case_id if diag else "CUSTOM-LAB",
            case_obj.issue_type if case_obj else "Custom",
            r.decision.capitalize(),
            r.verification_status,
            r.reviewer_name,
            r.reviewer_note,
            is_correction,
            diag.probable_root_cause if diag else "",
            diag.suggested_fix if diag else "",
            final_fix,
            r.reviewed_at
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="netsage_audit_report.csv"'}
    )


@app.get("/api/export/audit-report.json")
def export_audit_report_json(db: Session = Depends(get_db)):
    reviews = db.query(models.Review).order_by(desc(models.Review.id)).all()
    records = []
    for r in reviews:
        diag = r.diagnosis
        case_obj = db.query(models.Case).filter(models.Case.case_id == diag.case_id).first() if (diag and diag.case_id) else None
        records.append({
            "audit_id": f"AUDIT-{r.id:04d}",
            "review_id": r.id,
            "diagnosis_id": r.diagnosis_id,
            "case_id": diag.case_id if diag else "CUSTOM-LAB",
            "issue_type": case_obj.issue_type if case_obj else "Custom",
            "decision": r.decision,
            "verification_status": r.verification_status,
            "reviewer_name": r.reviewer_name,
            "reviewer_note": r.reviewer_note,
            "is_ai_correction": r.decision in ["edited", "rejected"],
            "ai_root_cause": diag.probable_root_cause if diag else "",
            "ai_suggested_fix": diag.suggested_fix if diag else "",
            "corrected_root_cause": r.corrected_root_cause,
            "final_approved_fix": r.corrected_fix if r.decision == "edited" else (diag.suggested_fix if diag else ""),
            "reviewed_at": r.reviewed_at
        })

    return JSONResponse(
        content={"audit_records": records, "exported_at": get_iso_timestamp()},
        headers={"Content-Disposition": 'attachment; filename="netsage_audit_report.json"'}
    )


# --- RESET DB API ---
@app.post("/api/admin/reset-db")
def reset_database():
    seed_db(force=True)
    return {"status": "success", "message": "Database reset to initial 30 real lab cases and 5 Responsible AI audit records"}


# --- FRONTEND ROUTE ---
@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>NetSage AI Frontend not found</h1>", status_code=404)
