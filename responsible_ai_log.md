# Responsible AI Audit Log - Human Oversight & AI Corrections

This document records **5+ documented incidents** where the NetSage AI diagnostic assistant generated an imprecise, incomplete, or hallucinated recommendation on Cisco Packet Tracer telemetry, and a human network engineer caught and corrected the error before deployment.

---

## 🛡️ Summary of Human Corrections

| Audit ID | Case ID | Fault Domain | AI Diagnostic Failure / Imprecision | Human Correction Applied | Verification Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AUDIT-001** | CASE-01 | VLAN / Trunking | AI identified port as access mode but forgot to ensure all required VLANs (VLAN 5 & 10) were active and Spanning Tree unblocked. | Human added `switchport mode trunk` and verified STP forwarding state across both subinterfaces. | **Verified** |
| **AUDIT-002** | CASE-05 | NAT / Security | AI suggested replacing the entire NAT pool instead of simply fixing the referenced standard ACL subnet statement. | Human corrected `access-list 1 permit 192.168.1.0 0.0.0.255`, preserving existing NAT pool definitions. | **Verified** |
| **AUDIT-003** | CASE-08 | NAT Configuration | AI suggested creating a new NAT pool when the pool and ACL were already correct and only the binding `overload` statement was missing. | Human inserted exact missing binding command: `ip nat inside source list 1 pool NATPOOL overload`. | **Verified** |
| **AUDIT-004** | CASE-21 | ACL Security | AI recommended deleting the entire access-list when only an explicit `permit ip any any` was needed to prevent implicit deny drops. | Human edited ACL to include `permit ip any any` without removing the targeted ICMP deny rule. | **Verified** |
| **AUDIT-005** | CASE-22 | Static Routing | AI recommended configuring an OSPF routing protocol instead of correcting the broken static route next-hop. | Human corrected the static route next-hop IP from `172.16.2.254` to `172.16.2.1` via `ip route 172.16.3.0 255.255.255.0 172.16.2.1`. | **Verified** |
| **AUDIT-006** | CASE-03 | DHCP Services | AI hallucinated that the DHCP service was turned off, missing that the pool network mask was shrunk to `/30`. | Human re-expanded the DHCP pool network mask to `255.255.255.0`, restoring lease acquisition. | **Verified** |

---

## 📝 Detailed Incident Reports

### Incident 1: AUDIT-001 (CASE-01 - Inter-VLAN Uplink Access Mode)
- **Reported Symptom**: PC1 (VLAN5) cannot communicate with Server1 (VLAN10) via router R1.
- **Initial AI Output**: Suggested re-creating VLANs 5 and 10 on the switch.
- **Why AI Was Incomplete**: The AI missed that the VLANs already existed in `show vlan brief`, and that the real root cause was `Gig0/1` being in access mode (`switchport mode access`) instead of 802.1Q trunking.
- **Human Engineer Action**: **Edited**. Reconfigured `interface gigabitEthernet 0/1` with `switchport mode trunk`.
- **Reviewer Note**: *"Human review caught missing trunk mode on SW1-R1 uplink; VLAN database was already healthy."*
- **Verification Status**: `Verified` (Web page at 10.10.10.1 loaded successfully).

---

### Incident 2: AUDIT-002 (CASE-05 - NAT Source ACL Mismatch)
- **Reported Symptom**: PC1 cannot reach remote host 172.16.2.1; no NAT translations occur.
- **Initial AI Output**: Proposed deleting and rebuilding the `ip nat pool` with new public IP addresses.
- **Why AI Was Incomplete**: The NAT pool `NATPOOL 172.16.1.50 172.16.1.60` was completely valid. The actual fault was that `access-list 1` permitted `192.168.2.0/24` instead of the local LAN `192.168.1.0/24`.
- **Human Engineer Action**: **Edited**. Corrected `access-list 1` source subnet to `192.168.1.0 0.0.0.255`.
- **Reviewer Note**: *"AI hallucinated a pool address issue. The real defect was ACL 1 subnet mismatch (192.168.2.0 vs 192.168.1.0)."*
- **Verification Status**: `Verified` (NAT translations populated in `show ip nat translations`).

---

### Incident 3: AUDIT-003 (CASE-08 - Missing NAT Binding Statement)
- **Reported Symptom**: Outbound traffic to 172.16.2.1 fails, no translations created.
- **Initial AI Output**: Suggested applying `ip nat inside` and `ip nat outside` to router interfaces.
- **Why AI Was Incomplete**: `Fa0/0` and `Fa0/1` already had `ip nat inside` and `ip nat outside` configured. The sole missing element was the global command `ip nat inside source list 1 pool NATPOOL overload`.
- **Human Engineer Action**: **Edited**. Issued `ip nat inside source list 1 pool NATPOOL overload`.
- **Reviewer Note**: *"Interfaces were already marked with NAT inside/outside. Only the binding overload command was omitted."*
- **Verification Status**: `Verified` (Ping succeeded with 0% loss).

---

### Incident 4: AUDIT-004 (CASE-21 - ACL Implicit Deny Drops Unintended Hosts)
- **Reported Symptom**: Both PC1 and PC2 are blocked after applying ACL 120, even though only PC2 was meant to be filtered.
- **Initial AI Output**: Recommended disabling ACL inspection on `FastEthernet0/0`.
- **Why AI Was Incomplete**: Disabling the ACL would violate security intent by unblocking PC2 as well. The proper fix was appending `permit ip any any` to negate the implicit deny.
- **Human Engineer Action**: **Edited**. Added `permit ip any any` to ACL 120.
- **Reviewer Note**: *"AI suggested removing security ACL entirely. Human engineer preserved the intentional deny rule while appending permit ip any any."*
- **Verification Status**: `Verified` (PC1 traffic passed, PC2 remained blocked as intended).

---

### Incident 5: AUDIT-005 (CASE-22 - Static Route Next-Hop Blackhole)
- **Reported Symptom**: PC2 cannot ping remote host 172.16.3.10; packets drop at R1.
- **Initial AI Output**: Suggested enabling dynamic routing (OSPF process 1) across R1 and R2.
- **Why AI Was Incomplete**: The lab uses static routing. Introducing OSPF would alter the required lab architecture. The actual defect was a typo in the static route (`172.16.2.254` instead of `172.16.2.1`).
- **Human Engineer Action**: **Edited**. Removed `172.16.2.254` static route and re-added `ip route 172.16.3.0 255.255.255.0 172.16.2.1`.
- **Reviewer Note**: *"Prevented AI architecture drift (introducing unrequested OSPF). Corrected static route next-hop to 172.16.2.1."*
- **Verification Status**: `Verified` (Ping to 172.16.3.10 returned 4 replies, 0% loss).
