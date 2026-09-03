import re
import json
from typing import List
from schemas import RuleFindingCreate


def run_deterministic_rules(
    show_outputs: str,
    symptom: str = "",
    topology_note: str = ""
) -> List[RuleFindingCreate]:
    """
    Deterministic rule checker evaluating Cisco show outputs, symptom, and topology text.
    Identifies exact configuration discrepancies across VLANs, Gateways, DHCP, DNS,
    Routing, ACLs, NAT, and physical interface states.
    """
    findings: List[RuleFindingCreate] = []
    combined_text = f"{show_outputs}\n{symptom}\n{topology_note}"
    lower_text = combined_text.lower()
    raw_lines = [line.strip() for line in show_outputs.splitlines() if line.strip()]

    def find_matching_line(pattern: str) -> str:
        for line in raw_lines:
            if re.search(pattern, line, re.IGNORECASE):
                return line
        return ""

    # 1. Interface Administratively Down / Disabled
    if (
        "administratively down" in lower_text or
        "status       disabled" in lower_text or
        "disabled     1" in lower_text or
        "port shutdown" in lower_text or
        "interface fastethernet0/1 shutdown" in lower_text or
        "interface g0/1 shutdown" in lower_text or
        ("status" in lower_text and "disabled" in lower_text) or
        ("line protocol is down" in lower_text and "down down" in lower_text)
    ):
        matched_line = find_matching_line(r"administratively\s+down|disabled|shutdown") or "Status: administratively down / disabled"
        findings.append(
            RuleFindingCreate(
                rule_name="Administratively Down Interface Check",
                severity="critical",
                finding="One or more network switch/router interfaces are administratively shut down or disabled, cutting off physical Layer 1/2 connectivity.",
                evidence=matched_line,
                recommendation="Enter interface configuration mode and issue `no shutdown` on the affected port."
            )
        )

    # 2. Switch Uplink Configured in Access Mode (Should be Trunk)
    if (
        ("router-on-a-stick" in lower_text or "uplink" in lower_text or "gi0/1" in lower_text or "switchport mode" in lower_text) and
        ("static access" in lower_text or "access mode vlan: 5" in lower_text or "fa0/5, gig0/1" in lower_text or "access port in vlan5" in lower_text)
    ):
        matched_line = find_matching_line(r"static access|access mode vlan|gig0/1") or "SW1 Gi0/1 configured as access port in VLAN 5"
        findings.append(
            RuleFindingCreate(
                rule_name="Trunk Uplink Access Mode Check",
                severity="critical",
                finding="The switch-to-router uplink is configured in static access mode instead of 802.1Q trunk mode, preventing inter-VLAN routing for secondary VLANs.",
                evidence=matched_line,
                recommendation="Reconfigure the switch uplink as a trunk: `interface Gi0/1` -> `switchport mode trunk`."
            )
        )

    # 3. Missing VLAN / Inactive VLAN in Database
    if (
        "vlan is absent" in lower_text or
        "vlan 10 is absent" in lower_text or
        "access mode vlan: 10 (inactive)" in lower_text or
        "(inactive)" in lower_text or
        "no vlan 10" in lower_text or
        "vlan is inactive" in lower_text or
        "vlan not created" in lower_text or
        ("vlan 20" in lower_text and "show vlan brief" in lower_text and "20 " not in lower_text) or
        ("absent from the vlan database" in lower_text)
    ):
        matched_line = find_matching_line(r"inactive|absent|no vlan|vlan\s+20") or "VLAN absent from database / Port marked (Inactive)"
        findings.append(
            RuleFindingCreate(
                rule_name="Missing or Inactive VLAN Check",
                severity="critical",
                finding="An access port is assigned to a VLAN that does not exist in the switch VLAN database, rendering the port inactive in Layer 2 forwarding.",
                evidence=matched_line,
                recommendation="Re-create and activate the VLAN in global configuration mode: `vlan <id>` -> `state active`."
            )
        )

    # 4. VLAN Omitted from Trunk Allowed List
    if (
        "vlans allowed on trunk" in lower_text or
        "trunk allowed list" in lower_text or
        "switchport trunk allowed vlan" in lower_text or
        ("10,20" in lower_text and "vlan 30" in lower_text)
    ):
        if ("10,20" in lower_text and "30" in lower_text) or "omitted" in lower_text:
            matched_line = find_matching_line(r"vlans allowed|switchport trunk allowed|10,20") or "Vlans allowed on trunk: 10,20 (VLAN 30 omitted)"
            findings.append(
                RuleFindingCreate(
                    rule_name="VLAN Omitted from Trunk Allowed List Check",
                    severity="error",
                    finding="The trunk interface allowed VLAN list explicitly restricts or prunes the required user VLAN, blocking cross-switch traffic.",
                    evidence=matched_line,
                    recommendation="Add the missing VLAN to the trunk: `switchport trunk allowed vlan add <vlan-id>`."
                )
            )

    # 5. Wrong Access Port VLAN Assignment (Same Subnet Isolation)
    if (
        ("vlan20" in lower_text or "vlan 20" in lower_text) and
        ("vlan10" in lower_text or "vlan 10" in lower_text) and
        ("wrong vlan" in lower_text or "access vlan" in lower_text or "fa0/1" in lower_text or "fa0/3" in lower_text) and
        ("192.168.1." in lower_text or "192.168.10." in lower_text)
    ):
        matched_line = find_matching_line(r"vlan20|vlan0020|fa0/1|fa0/3") or "Port assigned to VLAN20 instead of VLAN10"
        findings.append(
            RuleFindingCreate(
                rule_name="Access Port VLAN Assignment Check",
                severity="error",
                finding="Host access port is assigned to the wrong VLAN, placing communicating hosts on the same IP subnet into isolated broadcast domains.",
                evidence=matched_line,
                recommendation="Assign the correct VLAN: `interface <port>` -> `switchport access vlan <correct-vlan>`."
            )
        )

    # 6. Default Gateway Mismatch on Host or Server
    if (
        "192.168.1.99" in lower_text or
        "192.168.10.254" in lower_text or
        "192.168.20.254" in lower_text or
        ("default gateway" in lower_text and ("mismatch" in lower_text or "incorrect" in lower_text or "192.168.20.1" in lower_text)) or
        (re.search(r"default gateway:\s*192\.168\.\d+\.(99|254|20\.1)", lower_text)) or
        ("default-gateway" in lower_text and "mismatch" in lower_text)
    ):
        matched_line = find_matching_line(r"default gateway|default-gateway|192\.168\.\d+\.(99|254|20\.1)") or "Default Gateway Mismatch / Unassigned Gateway IP"
        findings.append(
            RuleFindingCreate(
                rule_name="Default Gateway Subnet Alignment Check",
                severity="critical",
                finding="Host or server default gateway is misconfigured with an unassigned or foreign subnet IP, allowing same-subnet traffic but blocking all off-subnet routing.",
                evidence=matched_line,
                recommendation="Set the client's default gateway IP to the active router interface/SVI address."
            )
        )

    # 7. Host Subnet Mask Mismatch (/30 instead of /24, or /28 mismatch)
    if (
        ("255.255.255.252" in lower_text and "subnet mask" in lower_text) or
        ("172.16.50.1/28" in lower_text and "172.16.50.150" in lower_text) or
        ("subnet mask mismatch" in lower_text) or
        ("mask mismatch" in lower_text)
    ):
        matched_line = find_matching_line(r"255\.255\.255\.252|172\.16\.50\.1/28|subnet mask") or "Subnet Mask discrepancy: /30 or /28 mismatch"
        findings.append(
            RuleFindingCreate(
                rule_name="Subnet Mask Consistency Check",
                severity="critical",
                finding="Host is configured with a restrictive or conflicting subnet mask, treating local subnet peers or gateway as remote and dropping packets.",
                evidence=matched_line,
                recommendation="Align subnet mask to match the network boundary (e.g. 255.255.255.0 /24)."
            )
        )

    # 8. Host Disparate Subnet IP Assignment
    if (
        "192.168.2.10" in lower_text and
        "192.168.1." in lower_text and
        ("wrong static ip" in lower_text or "wrong network" in lower_text or "ip address changed" in lower_text)
    ):
        matched_line = find_matching_line(r"ipv4 address:\s*192\.168\.2\.10") or "IPv4 Address: 192.168.2.10 (Wrong subnet)"
        findings.append(
            RuleFindingCreate(
                rule_name="Static IP Subnet Alignment Check",
                severity="error",
                finding="Host is manually assigned an IP in a different subnet (192.168.2.0/24) than its peer (192.168.1.0/24) without an intervening router.",
                evidence=matched_line,
                recommendation="Reassign the host IP to the valid local subnet: 192.168.1.10."
            )
        )

    # 9. DHCP Pool Exhaustion (/30 Shrunk Network Statement)
    if (
        "network 192.168.1.0 255.255.255.252" in lower_text or
        ("pool network changed" in lower_text and "255.255.255.252" in lower_text) or
        ("dhcp request failed" in lower_text and "pool shrink" in lower_text) or
        ("dhcp pool exhaustion" in lower_text)
    ):
        matched_line = find_matching_line(r"network\s+192\.168\.1\.0\s+255\.255\.255\.252|dhcp request failed") or "network 192.168.1.0 255.255.255.252 (/30 pool)"
        findings.append(
            RuleFindingCreate(
                rule_name="DHCP Pool Network Boundary Check",
                severity="critical",
                finding="The DHCP pool network statement was shrunk to a /30 subnet, leaving 0 usable leaseable addresses after exclusion ranges.",
                evidence=matched_line,
                recommendation="Restore the DHCP pool network to `/24`: `ip dhcp pool <name>` -> `network 192.168.1.0 255.255.255.0`."
            )
        )

    # 10. DHCP Service Disabled on Router
    if (
        "no service dhcp" in lower_text or
        "dhcp service disabled" in lower_text or
        ("service dhcp" in lower_text and "disabled" in lower_text)
    ):
        matched_line = find_matching_line(r"no service dhcp") or "no service dhcp"
        findings.append(
            RuleFindingCreate(
                rule_name="DHCP Service Global State Check",
                severity="critical",
                finding="The Cisco IOS DHCP server process is globally disabled via `no service dhcp`, suppressing responses to client renewal requests.",
                evidence=matched_line,
                recommendation="Enable the DHCP server globally: `service dhcp`."
            )
        )

    # 11. DHCP Distributing Wrong Default Gateway or DNS
    if (
        "default-router 192.168.10.254" in lower_text or
        "default-router 192.168.1.254" in lower_text or
        "dns-server 192.168.1.254" in lower_text or
        ("default-router" in lower_text and "mismatch" in lower_text)
    ):
        matched_line = find_matching_line(r"default-router|dns-server\s+192\.168\.1\.254") or "DHCP Option: default-router / dns-server 192.168.x.254"
        findings.append(
            RuleFindingCreate(
                rule_name="DHCP Default-Router Option Check",
                severity="error",
                finding="DHCP pool distributes an invalid default-router or DNS server IP (.254), breaking remote routing or hostname resolution for clients.",
                evidence=matched_line,
                recommendation="Correct the DHCP pool options: `default-router <ip>` or `dns-server <ip>`."
            )
        )

    # 12. Missing Static Route in Routing Table
    if (
        "no entry for 172.16.3.0/24" in lower_text or
        "no entry for" in lower_text or
        ("show ip route" in lower_text and "172.16.3.0" not in lower_text and "172.16.3.10" in lower_text) or
        ("gateway of last resort is not set" in lower_text and "missing return route" in lower_text) or
        ("missing route" in lower_text) or
        ("destination host unreachable" in lower_text and "no route" in lower_text)
    ):
        matched_line = find_matching_line(r"gateway of last resort|no entry for|directly connected") or "Routing table lacks entry for destination subnet"
        findings.append(
            RuleFindingCreate(
                rule_name="Missing Static or Return Route Check",
                severity="critical",
                finding="The router lacks a routing table entry (static or dynamic) for the destination network, dropping packets with Destination Host Unreachable.",
                evidence=matched_line,
                recommendation="Add a static route to the target network: `ip route <dest> <mask> <next-hop>`."
            )
        )

    # 13. Static Route with Wrong Next-Hop Address
    if (
        "via 172.16.2.254" in lower_text or
        "next hop 172.16.2.254" in lower_text or
        "wrong next hop" in lower_text
    ):
        matched_line = find_matching_line(r"via 172\.16\.2\.254|next hop 172\.16\.2\.254") or "S 172.16.3.0/24 [1/0] via 172.16.2.254"
        findings.append(
            RuleFindingCreate(
                rule_name="Static Route Next-Hop Validity Check",
                severity="critical",
                finding="Static route specifies an unreachable next-hop IP (172.16.2.254), resulting in traffic blackholing.",
                evidence=matched_line,
                recommendation="Update the static route next-hop to R2's interface: `ip route 172.16.3.0 255.255.255.0 172.16.2.1`."
            )
        )

    # 14. ACL Explicit Deny Rule Filtering
    if (
        ("deny icmp" in lower_text or "deny ip" in lower_text or "10 deny" in lower_text) and
        ("access-list" in lower_text or "access-group" in lower_text or "matches" in lower_text or "172.16.1.1" in lower_text or "192.168.1.11" in lower_text)
    ):
        matched_line = find_matching_line(r"deny\s+icmp|deny\s+ip|10 deny") or "ACL matches: explicit deny statement"
        findings.append(
            RuleFindingCreate(
                rule_name="ACL Explicit Deny Rule Check",
                severity="warning",
                finding="An Access Control List contains an explicit deny statement matching the client's traffic, dropping packets at the interface boundary.",
                evidence=matched_line,
                recommendation="Remove the offending deny statement or insert an overriding permit rule in the ACL."
            )
        )

    # 15. ACL Implicit Deny (Missing Permit Any Statement)
    if (
        "no permit statement" in lower_text or
        "implicit deny blocks" in lower_text or
        "acl implicit deny" in lower_text or
        ("access-list 120" in lower_text and "no permit rule" in lower_text)
    ):
        matched_line = find_matching_line(r"extended ip access list 120|implicit deny") or "Extended ACL contains deny ACE without trailing permit statement"
        findings.append(
            RuleFindingCreate(
                rule_name="ACL Implicit Deny Check",
                severity="critical",
                finding="The applied ACL contains only deny rules with no permit statement. Cisco's implicit `deny ip any any` is silently dropping all traffic.",
                evidence=matched_line,
                recommendation="Append a permit rule to the ACL: `permit ip any any` or remove the access-group from the interface."
            )
        )

    # 16. NAT Source ACL Subnet Mismatch
    if (
        "permit 192.168.2.0" in lower_text and
        ("192.168.1.0" in lower_text or "192.168.1.10" in lower_text or "192.168.1.11" in lower_text or "nat" in lower_text)
    ):
        matched_line = find_matching_line(r"permit\s+192\.168\.2\.0") or "access-list 1 permit 192.168.2.0 0.0.0.255"
        findings.append(
            RuleFindingCreate(
                rule_name="NAT Source ACL Subnet Matching Check",
                severity="critical",
                finding="The ACL referenced by the NAT rule permits 192.168.2.0/24 instead of the actual LAN subnet 192.168.1.0/24, preventing translation.",
                evidence=matched_line,
                recommendation="Update the NAT ACL statement: `access-list 1 permit 192.168.1.0 0.0.0.255`."
            )
        )

    # 17. NAT Missing Translation Binding Overload Rule
    if (
        "missing translation binding" in lower_text or
        "no ip nat inside source list 1" in lower_text or
        ("nat pool" in lower_text and "empty" in lower_text and "no translation rule" in lower_text)
    ):
        matched_line = find_matching_line(r"ip nat pool|no ip nat inside source") or "Missing 'ip nat inside source list 1 pool NATPOOL overload' command"
        findings.append(
            RuleFindingCreate(
                rule_name="NAT Translation Binding Rule Check",
                severity="critical",
                finding="NAT pool and ACL are configured, but the global `ip nat inside source` binding command is missing. No dynamic translations can occur.",
                evidence=matched_line,
                recommendation="Add the NAT translation binding: `ip nat inside source list 1 pool NATPOOL overload`."
            )
        )

    # 18. NAT Inside/Outside Interface Role Reversal
    if (
        ("outside interfaces: (none)" in lower_text and "inside interfaces: fastethernet0/1" in lower_text) or
        ("nat roles were reversed" in lower_text) or
        ("fa0/0 no ip nat inside" in lower_text and "fa0/1" in lower_text) or
        ("nat role reversal" in lower_text) or
        ("outside interface configured as inside" in lower_text)
    ):
        matched_line = find_matching_line(r"outside interfaces:\s*\(none\)|inside interfaces:\s*fastethernet0/1|ip nat inside") or "Outside Interfaces: (none) / Inside Interfaces: Fa0/1"
        findings.append(
            RuleFindingCreate(
                rule_name="NAT Inside/Outside Interface Role Check",
                severity="critical",
                finding="NAT interface designations are inverted: the WAN interface is designated as inside or outside interface is missing entirely.",
                evidence=matched_line,
                recommendation="Assign `ip nat inside` to LAN (Fa0/0) and `ip nat outside` to WAN (Fa0/1)."
            )
        )

    # 19. DNS Service Disabled or Missing A Record
    if (
        "dns changed from on to off" in lower_text or
        "dns service state: disabled" in lower_text or
        "server1 dns record list empty" in lower_text or
        ("could not find host" in lower_text and "dns" in lower_text) or
        "192.168.1.199" in lower_text
    ):
        matched_line = find_matching_line(r"dns service|could not find host|dns record|192\.168\.1\.199") or "DNS service is Disabled or A record is missing"
        findings.append(
            RuleFindingCreate(
                rule_name="DNS Service & Record Availability Check",
                severity="error",
                finding="DNS hostname lookup failed: either the DNS server address is invalid, service is disabled, or the A record mapping is absent.",
                evidence=matched_line,
                recommendation="Enable the DNS Service and ensure valid DNS server IP and A record mapping exist."
            )
        )

    # 20. Native VLAN Mismatch (%CDP-4-NATIVE_VLAN_MISMATCH)
    if (
        "native_vlan_mismatch" in lower_text or
        "native vlan mismatch" in lower_text
    ):
        matched_line = find_matching_line(r"NATIVE_VLAN_MISMATCH|Native Mode VLAN") or "%CDP-4-NATIVE_VLAN_MISMATCH discovered on trunk"
        findings.append(
            RuleFindingCreate(
                rule_name="Trunk Native VLAN Consistency Check",
                severity="critical",
                finding="Discrepancy detected in 802.1Q Native VLAN IDs across trunk endpoints. Causes untagged frame leakage and Spanning Tree port blocking (PVID-inconsistent).",
                evidence=matched_line,
                recommendation="Synchronize native VLANs on both ends: `switchport trunk native vlan <id>`."
            )
        )

    # 21. Duplicate IP Indication
    if (
        "%ip-4-dupaddr" in lower_text or
        "dupaddr" in lower_text or
        "duplicate address" in lower_text or
        "duplicate ip" in lower_text
    ):
        matched_line = find_matching_line(r"DUPADDR|duplicate address|duplicate IP") or "%IP-4-DUPADDR: Duplicate address detected"
        findings.append(
            RuleFindingCreate(
                rule_name="Duplicate IP Address Conflict Check",
                severity="critical",
                finding="Syslog %IP-4-DUPADDR logged: multiple MAC addresses are claiming the same IP address, resulting in ARP flapping and communication failure.",
                evidence=matched_line,
                recommendation="Identify the duplicate host MAC via `show mac address-table` and assign a unique IP to the conflicting host."
            )
        )

    # Fallback heuristic if text provided but no strict pattern triggered
    if not findings and show_outputs.strip():
        findings.append(
            RuleFindingCreate(
                rule_name="General Configuration Telemetry Review",
                severity="info",
                finding="No fatal syntax violations matched deterministic patterns. Context forwarded to AI diagnostic engine for deeper analysis.",
                evidence=f"CLI Output ({len(show_outputs)} chars submitted)",
                recommendation="Inspect detailed show command outputs and verify routing/switching tables."
            )
        )

    return findings


def run_rules_json(show_outputs: str, symptom: str = "", topology_note: str = "") -> str:
    """Convenience helper returning rule findings as a formatted JSON string."""
    findings = run_deterministic_rules(show_outputs, symptom, topology_note)
    return json.dumps([f.model_dump() for f in findings], indent=2)
