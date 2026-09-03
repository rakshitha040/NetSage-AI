# NetSage AI - Cisco Packet Tracer Troubleshooting Assistant

NetSage AI is an AI-assisted Cisco Packet Tracer network troubleshooting system with strict truthfulness grounding, deterministic rule verification, human-in-the-loop oversight, and responsible AI audit trails.

---

## 📦 Project Deliverables

| Deliverable Item | File Location | Description |
| :--- | :--- | :--- |
| **1. Dataset (`cases.csv`)** | [`data/cases.csv`](file:///d:/rakshitha/netsag-ai/data/cases.csv) | 30 real Cisco Packet Tracer lab cases with symptom, show outputs, expected fault, OSI layer, concept, severity, next command, and fix scripts. |
| **2. Prompt Files** | [`diagnose_prompt.md`](file:///d:/rakshitha/netsag-ai/diagnose_prompt.md) | Master troubleshooter prompt template enforcing strict JSON output (`root_cause`, `confidence`, `evidence`, `next_command`, `fix_steps`) and 3 worked lab examples. |
| **3. Python Rule Checker** | [`rules.py`](file:///d:/rakshitha/netsag-ai/rules.py) & [`checker.py`](file:///d:/rakshitha/netsag-ai/checker.py) | Python deterministic rule checker returning JSON findings for interface down, missing VLANs, wrong masks, gateway mismatches, missing routes, DHCP/DNS, ACL, and NAT. |
| **4. Web Analytics Dashboard** | [`index.html`](file:///d:/rakshitha/netsag-ai/index.html) | Single-file UI with fault domain charts, human agreement metrics, audit report ledger, and export buttons for CSV and JSON. |
| **5. Responsible AI Log** | [`responsible_ai_log.md`](file:///d:/rakshitha/netsag-ai/responsible_ai_log.md) | Documented incident reports on 5+ human corrections where AI was imprecise, hallucinated, or altered lab architecture. |

---

## ⚡ Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Rule Checker CLI (Standalone Python Checker)
```bash
python checker.py --sample
```

You can also evaluate custom telemetry:
```bash
python checker.py --symptom "PC cannot reach server" --show "Router# show ip interface brief"
```

### 3. Start the Web Server & UI
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Open your browser at **`http://127.0.0.1:8000`**.

### 4. Run Automated Test Suite
```bash
python -m pytest tests/ -v
```

---

## 🛡️ Truthfulness & Responsible AI Guarantee

- **Grounding**: AI evidence quotes are strictly copied verbatim from user-submitted CLI text.
- **Safety Disclaimer**: Every diagnosis output states: *"Human review is required before applying any fix."*
- **Human Authority**: Fixes are never automatically applied to network devices. Only a human reviewer can mark a lab fix as `Verified`.
