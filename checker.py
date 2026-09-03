#!/usr/bin/env python3
"""
NetSage AI - Python Deterministic Rule Checker CLI
Validates Cisco Packet Tracer telemetry and outputs structured JSON findings.
Checks for duplicate IPs, wrong masks, gateway mismatches, interface down states,
missing VLANs, and missing routes.
"""

import sys
import os
import json
import argparse
from rules import run_deterministic_rules

def check_telemetry(show_outputs: str, symptom: str = "", topology_note: str = "") -> dict:
    findings = run_deterministic_rules(show_outputs, symptom, topology_note)
    return {
        "status": "success",
        "findings_count": len(findings),
        "rule_findings": [f.model_dump() for f in findings]
    }

def main():
    parser = argparse.ArgumentParser(description="NetSage AI Deterministic Rule Checker")
    parser.add_argument("--symptom", type=str, default="", help="Reported network symptom")
    parser.add_argument("--topology", type=str, default="", help="Topology and device context")
    parser.add_argument("--show", type=str, default="", help="Cisco show command outputs")
    parser.add_argument("--file", type=str, help="Path to text file containing show outputs")
    parser.add_argument("--sample", action="store_true", help="Run with a sample case")

    args = parser.parse_args()

    show_text = args.show
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            show_text = f.read()

    if args.sample or (not show_text and not args.symptom):
        print("Running sample check on CASE-01 (Uplink in Access Mode):")
        sample_symptom = "PC1 (VLAN5) cannot communicate with Server1 (VLAN10) via router R1; web page at 10.10.10.1 fails."
        sample_topo = "PC1(VLAN5, Fa0/5) -> SW1 -> R1(router-on-a-stick) -> Server1(VLAN10, Fa0/10); SW1-R1 uplink on SW1 Gi0/1"
        sample_show = """SW1#show vlan brief
5   VLAN0005  active  Fa0/5, Gig0/1
10  VLAN0010  active  Fa0/10

SW1#show interfaces gigabitEthernet 0/1 switchport
Administrative Mode: static access
Operational Mode: static access
Access Mode VLAN: 5 (VLAN0005)"""
        result = check_telemetry(sample_show, sample_symptom, sample_topo)
        print(json.dumps(result, indent=2))
        return

    result = check_telemetry(show_text, args.symptom, args.topology)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
