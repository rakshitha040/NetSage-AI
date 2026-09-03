# NetSage AI — Project Executive Summary & Technical Documentation

---

## 📌 1. Executive Summary

**NetSage AI** is an AI-assisted, human-in-the-loop diagnostic system designed for troubleshooting Cisco network configurations in simulated Cisco Packet Tracer environments. Network engineers and lab students frequently encounter subtle, multi-layer faults across VLANs, dynamic routing, DHCP scopes, ACL filtering, NAT overloading, and physical/administrative interface states.

Traditional automated tools either execute unverified scripts directly against infrastructure or provide open-ended AI hallucinations without deterministic grounding. NetSage AI resolves this by coupling a **deterministic Cisco rule validation engine** with an **advisory AI diagnostic assistant**, governed strictly by a **mandatory human review and audit workflow**. Every fix must be verified by a human reviewer before deployment, guaranteeing operational safety, accountability, and explainability.

---

## 🎯 2. Core Objectives & Design Principles

1. **Truthfulness & Evidence Grounding**:
   - Diagnostic citations and evidence quotes are extracted **verbatim** strictly from user-provided Cisco CLI telemetry (`show` commands, syslog banners, `ipconfig` outputs).
   - No synthetic or hallucinated telemetry lines are permitted.

2. **Mandatory Human-in-the-Loop Oversight**:
   - AI outputs are classified strictly as **advisory recommendations**, never confirmed facts.
   - Every diagnosis response enforces the mandatory safety banner:  
     > *"Human review is required before applying any fix."*
   - Fixes are never automatically applied to network devices.
   - Only a human reviewer can assign the `Verified` lab status.

3. **Multi-Domain Network Coverage**:
   - Comprehensive coverage across 8 distinct network fault domains spanning OSI Layers 1, 2, 3, 4, and 7.

---

## 🔄 3. End-to-End Troubleshooting Workflow

```text
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. Telemetry Ingestion (Symptom + Topology + CLI Show Outputs)│
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 2. Deterministic Rule Checker (rules.py / checker.py)       │
  │    - Scans for admin down, missing VLANs, wrong masks,       │
  │      gateway mismatches, missing routes, ACLs, NAT          │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 3. Master Troubleshooter AI Assistant (ai_service.py)       │
  │    - Synthesizes findings + generates structured JSON        │
  │    - Confidence score (0-100), root cause, next command,    │
  │      verbatim evidence quotes, and Cisco IOS fix script     │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 4. Mandatory Human Review Panel (Workbench UI)              │
  │    - Reviewer selects: [Accepted] | [Edited] | [Rejected]   │
  │    - Mandatory reviewer rationale notes                     │
  │    - If "Edited", requires corrected root cause & fix script│
  │    - Verification status set strictly by human engineer     │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ 5. Immutable Audit Event & Analytics Ledger (app.py / DB)   │
  │    - Logs decision timestamp, reviewer name, corrections    │
  │    - Updates real-time KPI cards and fault distribution     │
  │    - Direct CSV and JSON export downloads                   │
  └─────────────────────────────────────────────────────────────┘
```

---

## 📦 4. Comprehensive Deliverables Breakdown

### 1. Lab Cases Dataset ([`data/cases.csv`](file:///d:/rakshitha/netsag-ai/data/cases.csv))
- Contains **30 real Cisco Packet Tracer lab scenarios** across all core networking domains.
- Standardized schema: `case_id`, `symptom`, `topology_note`, `show_outputs`, `expected_fault`, `osi_layer`, `concept`, `severity`, `expected_next_command`, `expected_fix`.

#### Fault Domain Distribution in Dataset:
- **Layer 1 & Interface States**: Port shutdown / administratively down transit links (`CASE-09`, `CASE-14`, `CASE-26`, `CASE-30`).
- **Layer 2 Data Link & VLANs**: Trunk access mode uplink, missing VLAN database, wrong access VLAN assignment, Native VLAN mismatch (`CASE-01`, `CASE-10`, `CASE-11`, `CASE-28`, `CASE-29`).
- **Layer 3 Addressing & Routing**: Default gateway mismatch, `/30` restrictive subnet mask, wrong static subnet IP, missing static route, static route next-hop blackhole (`CASE-02`, `CASE-06`, `CASE-12`, `CASE-13`, `CASE-22`, `CASE-25`, `CASE-27`).
- **Layer 4 ACL & Security**: Explicit host ICMP deny, implicit deny blocking unintended hosts (`CASE-04`, `CASE-18`, `CASE-21`).
- **NAT & Translation Overload**: Wrong ACL source subnet matching, missing translation binding rule, NAT inside/outside interface role reversal (`CASE-05`, `CASE-08`, `CASE-20`, `CASE-23`).
- **Layer 7 Application Services (DHCP & DNS)**: DHCP pool exhaustion (/30 scope), DHCP service disabled, incorrect DHCP gateway/DNS options, DNS service disabled, missing DNS A record (`CASE-03`, `CASE-07`, `CASE-15`, `CASE-16`, `CASE-17`, `CASE-19`, `CASE-24`).

---

### 2. Structured Prompt Specification ([`diagnose_prompt.md`](file:///d:/rakshitha/netsag-ai/diagnose_prompt.md))
- Master CCIE Troubleshooter system prompt enforcing strict, schema-validated JSON outputs.
- Requires `root_cause`, `confidence` (score & label), `osi_layer`, `evidence` (verbatim string array), `next_command`, `fix_steps`, `suggested_cisco_ios_fix`, and `safety_note`.
- Includes **3 complete worked Cisco Packet Tracer lab examples**:
  1. *Worked Example 1*: Inter-VLAN routing failure caused by switch uplink configured in static access mode (`CASE-01`).
  2. *Worked Example 2*: Client unable to reach remote networks due to default gateway mismatch (`CASE-02`).
  3. *Worked Example 3*: DHCP lease failure caused by pool network statement shrunk to `/30` (`CASE-03`).

---

### 3. Deterministic Python Rule Checker ([`rules.py`](file:///d:/rakshitha/netsag-ai/rules.py) & [`checker.py`](file:///d:/rakshitha/netsag-ai/checker.py))
- Standalone, explainable rule engine evaluating CLI outputs against deterministic patterns before and alongside AI diagnosis.
- Returns structured JSON findings containing `rule_name`, `severity` (`critical`, `error`, `warning`, `info`), `finding`, `evidence`, and `recommendation`.
- Standalone CLI interface:
  ```bash
  python checker.py --sample
  python checker.py --symptom "<symptom>" --show "<cli_output>"
  ```

---

### 4. Interactive Analytics Dashboard & Single-File Web UI ([`index.html`](file:///d:/rakshitha/netsag-ai/index.html))
- Standalone zero-build single-file frontend built with Tailwind CSS, Lucide icons, Chart.js, and Canvas-Confetti (delivered via CDN, no npm/node build step required).
- **Diagnostic Workbench**: Preloads all 30 lab cases, allows custom telemetry entry, displays deterministic rule matches alongside AI diagnostic proposals, and renders the mandatory human review form.
- **Analytics & Audit Ledger**: Live summary KPI cards, network fault domain bar chart, human decision breakdown progress bars, responsible AI badge filters, and direct download links for:
  - `GET /api/export/audit-report.csv`
  - `GET /api/export/cases.csv`
  - `GET /api/export/audit-report.json`

---

### 5. Responsible AI Audit Log ([`responsible_ai_log.md`](file:///d:/rakshitha/netsag-ai/responsible_ai_log.md))
- Records **5+ documented incidents** illustrating where human oversight caught AI hallucinations, improper scope changes, or architecture drift:
  1. **AUDIT-001 (CASE-01)**: AI suggested re-creating existing VLANs; human caught that uplink port `Gi0/1` was in access mode and configured 802.1Q trunking.
  2. **AUDIT-002 (CASE-05)**: AI proposed replacing the NAT pool; human identified that only the referenced standard ACL subnet statement had a typo (`192.168.2.0` vs `192.168.1.0`).
  3. **AUDIT-003 (CASE-08)**: AI suggested re-applying interface roles; human caught that interfaces were already correct and only the global binding `overload` command was omitted.
  4. **AUDIT-004 (CASE-21)**: AI recommended removing the entire ACL; human preserved security intent by adding `permit ip any any` to negate implicit deny.
  5. **AUDIT-005 (CASE-22)**: AI hallucinated switching the entire lab to OSPF routing; human corrected the static route next-hop IP (`172.16.2.254` ➔ `172.16.2.1`), preserving lab architecture.

---

## 💻 5. Technology Stack

| Layer | Component / Tool | Role in Architecture |
| :--- | :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.10+) | High-performance asynchronous REST API handling telemetry analysis, review recording, and exports. |
| **Database & ORM** | SQLite3 + SQLAlchemy | Lightweight local persistence (`netsage.db`) for cases, diagnoses, rule findings, reviews, and audit events. |
| **Data Validation** | Pydantic v2 | Strict schema validation enforcing mandatory reviewer notes and edited correction fields. |
| **Frontend UI** | HTML5, Tailwind CSS, Vanilla JS | Zero-build single-file web application with dark CLI terminal styling and live interactive charts. |
| **Visualization** | Chart.js | Dynamic rendering of network fault domain distribution and human decision ratios. |
| **Testing Engine** | Pytest + HTTPX | Automated unit and integration test suite with 100% test pass rate. |

---

## 🧪 6. Testing & Quality Assurance

The automated test suite in [`tests/`](file:///d:/rakshitha/netsag-ai/tests) verifies all core endpoints and deterministic rule checks:

```bash
$ python -m pytest tests/ -v
============================= test session starts =============================
tests/test_api.py::test_health_endpoint PASSED                           [  4%]
tests/test_api.py::test_dashboard_summary PASSED                         [  9%]
tests/test_api.py::test_cases_listing_and_detail PASSED                  [ 14%]
tests/test_api.py::test_csv_import_missing_headers PASSED                [ 19%]
tests/test_api.py::test_csv_import_valid PASSED                          [ 23%]
tests/test_api.py::test_create_diagnosis PASSED                          [ 28%]
tests/test_api.py::test_review_validation_mandatory_notes PASSED         [ 33%]
tests/test_api.py::test_review_validation_mandatory_edited_fields PASSED [ 38%]
tests/test_api.py::test_review_submission_success PASSED                 [ 42%]
tests/test_api.py::test_audit_log_and_exports PASSED                     [ 47%]
tests/test_rules.py::test_administratively_down_rule PASSED              [ 52%]
tests/test_rules.py::test_missing_or_inactive_vlan_rule PASSED           [ 57%]
tests/test_rules.py::test_vlan_omitted_from_trunk_allowed_list PASSED    [ 61%]
tests/test_rules.py::test_default_gateway_mismatch PASSED                [ 66%]
tests/test_rules.py::test_subnet_mask_mismatch PASSED                    [ 71%]
tests/test_rules.py::test_missing_static_or_return_route PASSED          [ 76%]
tests/test_rules.py::test_dhcp_default_router_mismatch PASSED            [ 80%]
tests/test_rules.py::test_acl_explicit_and_implicit_deny PASSED          [ 85%]
tests/test_rules.py::test_nat_role_reversal PASSED                       [ 90%]
tests/test_rules.py::test_duplicate_ip_indication PASSED                 [ 95%]
tests/test_rules.py::test_native_vlan_mismatch PASSED                    [100%]

============================= 21 passed in 1.49s ==============================
```

---

## 🔗 7. Official Project Repository

The complete source code, dataset, prompt specifications, rule checker, test suite, and audit reports are documented and maintained on GitHub:

👉 **[https://github.com/rakshitha040/NetSage-AI](https://github.com/rakshitha040/NetSage-AI)**
