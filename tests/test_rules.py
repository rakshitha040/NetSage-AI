import pytest
from rules import run_deterministic_rules


def test_administratively_down_rule():
    show_output = """
Router# show ip interface brief
GigabitEthernet0/0/0       192.168.1.1     YES manual administratively down down
GigabitEthernet0/0/1       10.0.0.1        YES manual up                    up
    """
    findings = run_deterministic_rules(show_output, symptom="Interface is down", topology_note="Core router")
    rule_names = [f.rule_name for f in findings]
    assert "Administratively Down Interface Check" in rule_names
    admin_down_finding = next(f for f in findings if f.rule_name == "Administratively Down Interface Check")
    assert admin_down_finding.severity == "critical"
    assert "no shutdown" in admin_down_finding.recommendation


def test_missing_or_inactive_vlan_rule():
    show_output = """
Switch-1# show interfaces FastEthernet0/5 status
Port      Name               Status       Vlan       Duplex  Speed Type
Fa0/5     Accounting-PC      connected    20         a-full  a-100 10/100BaseTX

Switch-1# show vlan brief
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Fa0/1, Fa0/2
10   Sales                            active    Fa0/7, Fa0/8
    """
    symptom = "Port is assigned to VLAN 20 but VLAN is inactive"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Access switch")
    rule_names = [f.rule_name for f in findings]
    assert "Missing or Inactive VLAN Check" in rule_names
    vlan_finding = next(f for f in findings if f.rule_name == "Missing or Inactive VLAN Check")
    assert vlan_finding.severity in ["error", "critical"]
    assert "vlan" in vlan_finding.recommendation.lower()


def test_vlan_omitted_from_trunk_allowed_list():
    show_output = """
A-SW1# show interfaces trunk
Port        Mode             Encapsulation  Status        Native vlan
Gi0/1       on               802.1q         trunking      1

Port        Vlans allowed on trunk
Gi0/1       10,20
    """
    symptom = "HR PCs on VLAN 30 cannot reach default gateway across trunk link"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Trunk Gi0/1")
    rule_names = [f.rule_name for f in findings]
    assert "VLAN Omitted from Trunk Allowed List Check" in rule_names
    trunk_finding = next(f for f in findings if f.rule_name == "VLAN Omitted from Trunk Allowed List Check")
    assert trunk_finding.severity == "error"
    assert "switchport trunk allowed vlan add" in trunk_finding.recommendation


def test_default_gateway_mismatch():
    show_output = """
PC-1> ipconfig
IP Address......................: 192.168.10.50
Subnet Mask.....................: 255.255.255.0
Default Gateway.................: 192.168.20.1
    """
    symptom = "PC cannot reach outside network; default gateway mismatch"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="PC to Router")
    rule_names = [f.rule_name for f in findings]
    assert "Default Gateway Subnet Alignment Check" in rule_names
    gw_finding = next(f for f in findings if f.rule_name == "Default Gateway Subnet Alignment Check")
    assert gw_finding.severity == "critical"


def test_subnet_mask_mismatch():
    show_output = """
Router# show ip interface GigabitEthernet0/0
GigabitEthernet0/0 is up, line protocol is up
  Internet address is 172.16.50.1/28

Server-A> ipconfig /all
   IPv4 Address. . . . . . . . . . . : 172.16.50.150
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
    """
    symptom = "Server cannot communicate with default gateway due to mask mismatch"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Server subnet")
    rule_names = [f.rule_name for f in findings]
    assert "Subnet Mask Consistency Check" in rule_names
    mask_finding = next(f for f in findings if f.rule_name == "Subnet Mask Consistency Check")
    assert mask_finding.severity == "critical"


def test_missing_static_or_return_route():
    show_output = """
Router# show ip route
Gateway of last resort is not set

      10.0.0.0/24 is subnetted, 1 subnets
C        10.0.0.0 is directly connected, GigabitEthernet0/0
    """
    symptom = "No route to host 192.168.1.0/24; missing return route"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Branch router")
    rule_names = [f.rule_name for f in findings]
    assert "Missing Static or Return Route Check" in rule_names
    route_finding = next(f for f in findings if f.rule_name == "Missing Static or Return Route Check")
    assert "ip route" in route_finding.recommendation


def test_dhcp_default_router_mismatch():
    show_output = """
Router# show running-config | section dhcp
ip dhcp pool LAN_POOL
 network 192.168.10.0 255.255.255.0
 default-router 192.168.10.254

Router# show ip interface brief | include GigabitEthernet0/0
GigabitEthernet0/0         192.168.10.1    YES manual up                    up
    """
    symptom = "DHCP clients receive wrong gateway 192.168.10.254 causing default router mismatch"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="DHCP on Router")
    rule_names = [f.rule_name for f in findings]
    assert "DHCP Default-Router Option Check" in rule_names


def test_acl_explicit_and_implicit_deny():
    show_output = """
Router# show access-lists
Extended IP access list OUTSIDE_IN
    10 deny ip any host 192.168.1.50 (42 matches)
    20 permit tcp any any established
    """
    symptom = "Traffic to 192.168.1.50 blocked by ACL deny statement"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Edge firewall")
    rule_names = [f.rule_name for f in findings]
    assert "ACL Explicit Deny Rule Check" in rule_names


def test_nat_role_reversal():
    show_output = """
Router# show running-config interface GigabitEthernet0/0
interface GigabitEthernet0/0
 description WAN Interface to ISP
 ip nat inside
!
interface GigabitEthernet0/1
 description LAN Interface
 ip nat outside
    """
    symptom = "NAT role reversal: outside interface configured as inside"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="NAT Gateway")
    rule_names = [f.rule_name for f in findings]
    assert "NAT Inside/Outside Interface Role Check" in rule_names


def test_duplicate_ip_indication():
    show_output = """
Switch# show logging
%IP-4-DUPADDR: Duplicate address 192.168.1.100 on GigabitEthernet0/1, sourced by 0011.2233.4455
    """
    symptom = "Intermittent drops, duplicate IP detected"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Access switch")
    rule_names = [f.rule_name for f in findings]
    assert "Duplicate IP Address Conflict Check" in rule_names


def test_native_vlan_mismatch():
    show_output = """
Switch-A# show logging
%CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on GigabitEthernet0/1 (1), with Switch-B GigabitEthernet0/1 (99).
    """
    symptom = "CDP native VLAN mismatch error"
    findings = run_deterministic_rules(show_output, symptom=symptom, topology_note="Switch-A to Switch-B")
    rule_names = [f.rule_name for f in findings]
    assert "Trunk Native VLAN Consistency Check" in rule_names
