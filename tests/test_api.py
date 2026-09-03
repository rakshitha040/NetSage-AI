import pytest
from fastapi.testclient import TestClient
from app import app, seed_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def init_db():
    seed_db()


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "NetSage AI"


def test_dashboard_summary():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_cases" in data
    assert "human_agreement_rate" in data
    assert "issue_type_counts" in data
    assert "severity_counts" in data


def test_cases_listing_and_detail():
    response = client.get("/api/cases")
    assert response.status_code == 200
    cases = response.json()
    assert isinstance(cases, list)
    assert len(cases) > 0

    first_case = cases[0]
    case_id = first_case["case_id"]

    detail_res = client.get(f"/api/cases/{case_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["case_id"] == case_id

    # 404 test
    not_found = client.get("/api/cases/NON_EXISTENT_CASE_999")
    assert not_found.status_code == 404


def test_csv_import_missing_headers():
    bad_csv = "bad_header_1,bad_header_2\nval1,val2"
    response = client.post("/api/cases/import-csv", data={"raw_csv": bad_csv})
    assert response.status_code == 400
    assert "missing required headers" in response.json()["detail"].lower()


def test_csv_import_valid():
    valid_csv = (
        "case_id,issue_type,topology_note,symptom,show_outputs,expected_fault,osi_layer,concept,severity,expected_next_command,expected_fix\n"
        "TEST-EXP-01,VLAN,Lab Test Switch,PC cannot communicate on VLAN 50,Switch# show vlan brief,VLAN 50 missing,Layer 2,Missing VLAN,High,show vlan,vlan 50"
    )
    response = client.post("/api/cases/import-csv", data={"raw_csv": valid_csv})
    assert response.status_code == 200
    data = response.json()
    assert data["imported_count"] >= 1
    assert data["failed_count"] == 0

    # Verify source_status is 'experiment'
    check = client.get("/api/cases/TEST-EXP-01")
    assert check.status_code == 200
    assert check.json()["source_status"] == "experiment"


def test_create_diagnosis():
    payload = {
        "case_id": "TEST-EXP-01",
        "topology_note": "Switch Fa0/1 to Server",
        "symptom": "Interface administratively down and traffic failing",
        "show_outputs": "Switch# show ip interface brief\nFastEthernet0/1 192.168.1.1 YES manual administratively down down"
    }
    response = client.post("/api/diagnoses", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["safety_note"] == "Human review is required before applying any fix."
    assert len(data["rule_findings"]) > 0
    assert data["rule_findings"][0]["severity"] == "critical"
    assert "no shutdown" in data["suggested_fix"].lower() or "no shutdown" in data["rule_findings"][0]["recommendation"].lower()


def test_review_validation_mandatory_notes():
    # 1. Create a diagnosis first
    diag_res = client.post("/api/diagnoses", json={
        "symptom": "Cannot reach gateway",
        "show_outputs": "Router# show ip route\nGateway of last resort is not set"
    })
    diag_id = diag_res.json()["id"]

    # 2. Try to submit review with empty reviewer notes -> Expect 422 Unprocessable Entity
    bad_review = {
        "diagnosis_id": diag_id,
        "decision": "accepted",
        "reviewer_note": "   ",
        "verification_status": "verified"
    }
    res = client.post("/api/reviews", json=bad_review)
    assert res.status_code == 422


def test_review_validation_mandatory_edited_fields():
    diag_res = client.post("/api/diagnoses", json={
        "symptom": "VLAN issue",
        "show_outputs": "Switch# show interfaces trunk\nVlans allowed on trunk: 10,20"
    })
    diag_id = diag_res.json()["id"]

    # Decision is edited, but corrected_fix is missing
    bad_edit = {
        "diagnosis_id": diag_id,
        "decision": "edited",
        "reviewer_note": "AI missed VLAN 30",
        "corrected_root_cause": "Trunk allowed list missing VLAN 30",
        "corrected_fix": "",  # Empty
        "verification_status": "fix_applied"
    }
    res = client.post("/api/reviews", json=bad_edit)
    assert res.status_code == 422


def test_review_submission_success():
    diag_res = client.post("/api/diagnoses", json={
        "symptom": "Native VLAN mismatch",
        "show_outputs": "%CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on GigabitEthernet0/1 (1), with Switch-B (99)."
    })
    diag_id = diag_res.json()["id"]

    valid_review = {
        "diagnosis_id": diag_id,
        "decision": "edited",
        "reviewer_note": "Corrected native VLAN to 99 on Switch-A and added clear STP command.",
        "corrected_root_cause": "Native VLAN 1 vs 99 mismatch on trunk Gi0/1",
        "corrected_fix": "interface Gi0/1\n switchport trunk native vlan 99",
        "verification_status": "verified",
        "reviewer_name": "Senior NetOps Engineer"
    }
    res = client.post("/api/reviews", json=valid_review)
    assert res.status_code == 200
    rev_data = res.json()
    assert rev_data["decision"] == "edited"
    assert rev_data["verification_status"] == "verified"


def test_audit_log_and_exports():
    # Audit log
    audit_res = client.get("/api/audit-log")
    assert audit_res.status_code == 200
    assert isinstance(audit_res.json(), list)

    # Cases CSV Export
    csv_cases_res = client.get("/api/export/cases.csv")
    assert csv_cases_res.status_code == 200
    assert "case_id,issue_type" in csv_cases_res.text

    # Audit Report CSV Export
    csv_audit_res = client.get("/api/export/audit-report.csv")
    assert csv_audit_res.status_code == 200
    assert "audit_id,case_id" in csv_audit_res.text

    # Audit Report JSON Export
    json_audit_res = client.get("/api/export/audit-report.json")
    assert json_audit_res.status_code == 200
    assert "audit_records" in json_audit_res.json()
