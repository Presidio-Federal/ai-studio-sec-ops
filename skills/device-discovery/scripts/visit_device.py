#!/usr/bin/env python3
"""Device map visit.

collect runs under execution_type mcp_orchestration. One run reads
inventory/network.json, calls one platform per device, and writes the
interface map and firewall files. It does not print tool bodies.

  python3 <skill>/scripts/visit_device.py collect --workspace <file_explorer> [--device "<name>"]
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workspace-handoff" / "scripts"))
try:
    import visit_common
except ImportError:
    print(
        '{"error": "visit_common missing; attach the workspace-handoff skill"}',
        file=sys.stderr,
    )
    sys.exit(1)

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
BUDGET_SECONDS = 240
IOS_KINDS = ("GigabitEthernet", "TenGigabitEthernet", "Ethernet", "Loopback", "Vlan", "Port-channel")
IOS_FIELDS = "GigabitEthernet(name;ip/address/primary);TenGigabitEthernet(name;ip/address/primary);Ethernet(name;ip/address/primary);Loopback(name;ip/address/primary);Vlan(name;ip/address/primary);Port-channel(name;ip/address/primary)"
IOS_FIELDS_NARROW = "GigabitEthernet(name;ip/address/primary);Loopback(name;ip/address/primary);Vlan(name;ip/address/primary)"
CDP_FIELDS = "cdp-neighbor-detail(device-name;local-intf-name;port-id;ip-address;platform-name)"
SAFE_FILE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
SAFE_ID = re.compile(r"^[0-9a-fA-F-]{8,64}$")
STAMP_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")
CURRENT = "network/endpoints/current.json"
METADATA = "network/endpoints/metadata.json"


def mask_to_prefix(mask):
    try:
        parts = [int(part) for part in str(mask).split(".")]
    except ValueError:
        return None
    if len(parts) != 4 or any(part < 0 or part > 255 for part in parts):
        return None
    bits = "".join(f"{part:08b}" for part in parts)
    if "01" in bits:
        return None
    return bits.count("1")


def cidr_from(address, mask):
    if not isinstance(address, str) or not address.strip():
        return None
    ip = address.strip()
    if isinstance(mask, int) or (isinstance(mask, str) and mask.isdigit()):
        prefix = int(mask)
        if 0 <= prefix <= 32:
            return f"{ip}/{prefix}"
        return ip
    if isinstance(mask, str) and "." in mask:
        prefix = mask_to_prefix(mask)
        if prefix is not None:
            return f"{ip}/{prefix}"
    return ip


def ftd_cidr(ipv4):
    if not isinstance(ipv4, dict):
        return None
    addr = ipv4.get("ipAddress") or {}
    if not isinstance(addr, dict):
        return None
    return cidr_from(addr.get("ipAddress"), addr.get("netmask"))


def ios_cidr(row):
    primary = ((row.get("ip") or {}).get("address") or {}).get("primary") or {}
    if not isinstance(primary, dict):
        return None
    return cidr_from(primary.get("address"), primary.get("mask"))


def as_list(value):
    if isinstance(value, list):
        return [item for item in value if item is not None]
    if isinstance(value, dict):
        return [value]
    return []


def first_address(value):
    if isinstance(value, str) and value.strip() and " " not in value:
        return value.strip()[:64]
    if isinstance(value, list):
        for item in value:
            found = first_address(item)
            if found:
                return found
    if isinstance(value, dict):
        for key in ("address", "ip", "ip-address"):
            found = first_address(value.get(key))
            if found:
                return found
    return None


def clean_text(value, limit=128):
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] if text else None


def label_text(value, limit=128):
    text = clean_text(value, limit)
    if text is None or " " in text:
        return None
    return text


def ios_interface_name(kind, raw):
    text = label_text(raw)
    if text is None:
        return None
    if text.lower().startswith(kind.lower()):
        return text
    return f"{kind}{text}"


def firewall_rel(name):
    if not isinstance(name, str) or SAFE_FILE.fullmatch(name) is None:
        return None
    return f"network/firewall/{name}.json"


def interface_key(device, row):
    label = row.get("hardware") or row.get("name")
    if not isinstance(device, str) or not isinstance(label, str):
        return None
    if " " in device or " " in label:
        return None
    return f"interface:{device}/{label}"


def device_key(name):
    if not isinstance(name, str) or not name or " " in name:
        return None
    return f"device:{name}"


def ref_names(items):
    names = []
    for item in as_list(items):
        if isinstance(item, str) and label_text(item):
            names.append(label_text(item))
        elif isinstance(item, dict):
            text = label_text(item.get("name")) or label_text(item.get("value"))
            if text:
                names.append(text)
    return list(dict.fromkeys(names))


def find_interface_tree(node, depth=0):
    if depth > 6 or not isinstance(node, dict):
        return None
    if any(kind in node for kind in IOS_KINDS):
        return node
    for value in node.values():
        if isinstance(value, dict):
            found = find_interface_tree(value, depth + 1)
            if found is not None:
                return found
    return None


def find_key(node, key, depth=0):
    if depth > 6:
        return None
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = find_key(value, key, depth + 1)
            if found is not None:
                return found
    return None


def parse_ios_interfaces(data):
    tree = find_interface_tree(data)
    rows = []
    if not isinstance(tree, dict):
        return rows
    for kind in IOS_KINDS:
        for item in as_list(tree.get(kind)):
            if not isinstance(item, dict):
                continue
            name = ios_interface_name(kind, item.get("name"))
            if name is None:
                continue
            parent = None
            out_kind = {"Loopback": "loopback", "Vlan": "vlan"}.get(kind, "physical")
            vlan = None
            if "." in name:
                parent = name.rsplit(".", 1)[0]
                out_kind = "subinterface"
            if kind == "Vlan" and str(item.get("name")).strip().isdigit():
                vlan = int(str(item.get("name")).strip())
            rows.append({
                "name": name,
                "hardware": None,
                "cidr": ios_cidr(item),
                "kind": out_kind,
                "parent": parent,
                "vlan": vlan,
                "zone": None,
                "mode": None,
                "link_state": None,
                "management_only": False,
            })
    return rows


def parse_cdp(data):
    raw = find_key(data, "cdp-neighbor-detail")
    rows = []
    for item in as_list(raw):
        if not isinstance(item, dict):
            continue
        local = label_text(item.get("local-intf-name"))
        neighbor = clean_text(item.get("device-name"), 200)
        port = label_text(item.get("port-id")) or clean_text(item.get("port-id"), 128)
        if not local or not neighbor:
            continue
        rows.append({
            "local_interface": local,
            "device": neighbor,
            "port": port,
            "address": first_address(item.get("ip-address")),
            "platform": clean_text(item.get("platform-name"), 128),
        })
    rows.sort(key=lambda row: (row["local_interface"], row["device"], row["port"] or ""))
    return rows


def parse_ftd_interface(item, parent, zones):
    if not isinstance(item, dict):
        return None
    hardware = label_text(item.get("hardwareName"))
    name = label_text(item.get("name")) or hardware
    if name is None:
        return None
    kind = "subinterface" if item.get("type") == "subinterface" or parent else "physical"
    vlan = item.get("vlanId")
    if isinstance(vlan, bool) or not isinstance(vlan, int):
        vlan = None
    link = label_text(item.get("linkState"))
    mode = label_text(item.get("mode"))
    return {
        "name": name,
        "hardware": hardware,
        "cidr": ftd_cidr(item.get("ipv4")),
        "kind": kind,
        "parent": parent,
        "vlan": vlan,
        "zone": zones.get(hardware) if hardware else None,
        "mode": mode,
        "link_state": link,
        "management_only": item.get("managementOnly") is True,
    }


def parse_zones(items):
    zones = []
    by_hardware = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = label_text(item.get("name"))
        if name is None:
            continue
        hardwares = []
        for ref in as_list(item.get("interfaces")):
            if not isinstance(ref, dict):
                continue
            hardware = label_text(ref.get("hardwareName"))
            if hardware:
                hardwares.append(hardware)
                by_hardware[hardware] = name
        zones.append({"name": name, "interfaces": hardwares})
    zones.sort(key=lambda row: row["name"])
    return zones, by_hardware


def parse_objects(items):
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = label_text(item.get("name"))
        if name is None:
            continue
        value = item.get("value")
        rows.append({
            "name": name,
            "kind": label_text(item.get("subType")) or "unknown",
            "value": value.strip()[:128] if isinstance(value, str) and value.strip() else None,
            "system": item.get("isSystemDefined") is True,
        })
    rows.sort(key=lambda row: row["name"])
    return rows


def parse_rules(policy_name, items):
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = label_text(item.get("name"))
        if name is None and item.get("ruleId") is not None:
            name = label_text(str(item.get("ruleId")))
        action = label_text(item.get("ruleAction"))
        if name is None or action is None:
            continue
        rows.append({
            "name": name,
            "policy": policy_name,
            "action": action,
            "source_zones": ref_names(item.get("sourceZones")),
            "destination_zones": ref_names(item.get("destinationZones")),
            "source_networks": ref_names(item.get("sourceNetworks")),
            "destination_networks": ref_names(item.get("destinationNetworks")),
            "source_ports": ref_names(item.get("sourcePorts")),
            "destination_ports": ref_names(item.get("destinationPorts")),
        })
    rows.sort(key=lambda row: (row["policy"] or "", row["name"]))
    return rows


def apply_keys(device_name, interfaces):
    keyed = []
    for row in interfaces:
        key = interface_key(device_name, row)
        if key is None:
            continue
        item = dict(row)
        item["keys"] = [key]
        keyed.append(item)
    keyed.sort(key=lambda row: (row.get("hardware") or row["name"], row["name"]))
    return keyed


def row_keys(device_name, interfaces):
    keys = []
    device = device_key(device_name)
    if device:
        keys.append(device)
    for row in interfaces:
        keys.extend(row.get("keys") or [])
    return list(dict.fromkeys(keys))


def resolve_workspace(given):
    raw = Path(given)
    ordered = [raw] if raw.is_absolute() else [Path.cwd() / raw]
    ordered.append(Path(__file__).resolve().parents[3] / "file_explorer")
    seen = []
    existing = []
    for path in ordered:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.append(resolved)
        if (resolved / "inventory" / "network.json").is_file():
            print(f"device workspace={resolved}", file=sys.stderr)
            return resolved
        if resolved.is_dir():
            existing.append(resolved)
    if existing:
        print(f"device workspace={existing[0]}", file=sys.stderr)
        return existing[0]
    print('{"error": "workspace directory missing"}', file=sys.stderr)
    return None


def checked_at(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh_stamp_id(ws, moment):
    folder = Path(ws) / "network" / "endpoints"
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        name = moment.strftime("%Y-%m-%dT%H-%M-%SZ")
        if STAMP_NAME.fullmatch(name) and not (folder / f"{name}.json").exists():
            return name
        moment = moment + timedelta(seconds=1)


def prune_stamps(ws):
    folder = Path(ws) / "network" / "endpoints"
    if not folder.is_dir():
        return
    stamps = sorted(
        path for path in folder.glob("*.json")
        if path.is_file() and STAMP_NAME.fullmatch(path.stem)
    )
    for path in stamps[:-10]:
        path.unlink()


def validate(instance, schema_name):
    import jsonschema

    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(instance)


def call_tool(name, args):
    body, err = visit_common.tool_body(visit_common.mcp_call(name, args))
    if err:
        return None, err
    return body, None


def ios_get(host, port, path, fields):
    args = {
        "path": path,
        "port": int(port),
        "params": {"fields": fields},
    }
    if host:
        args["host"] = host
    body, err = call_tool("iosxe_restconf_get", args)
    if err:
        return None, err
    return body.get("data"), None


def ftd_get(host, port, path, params=None):
    args = {"path": path, "port": int(port)}
    if host:
        args["host"] = host
    if params:
        args["params"] = params
    body, err = call_tool("ftd_get", args)
    if err:
        return None, err
    return body.get("data"), None


def ftd_items(host, port, path):
    items = []
    offset = 0
    while offset <= 1000:
        data, err = ftd_get(host, port, path, {"limit": 100, "offset": offset})
        if err:
            return None, err
        if not isinstance(data, dict):
            return None, "list was not an object"
        page = data.get("items") or []
        if not isinstance(page, list):
            return None, "items was not a list"
        items.extend(item for item in page if isinstance(item, dict))
        count = (data.get("paging") or {}).get("count")
        offset += len(page)
        if not page or not isinstance(count, int) or offset >= count:
            break
    return items, None


def restconf_port(device):
    access = device.get("access") if isinstance(device.get("access"), dict) else {}
    restconf = access.get("restconf")
    if not isinstance(restconf, dict):
        return None
    port = restconf.get("port")
    if isinstance(port, bool) or not isinstance(port, int):
        return None
    if port < 1 or port > 65535:
        return None
    return port


def selectable(device):
    platform = device.get("platform")
    if platform not in {"iosxe", "ftd"}:
        return False
    if device_key(device.get("name")) is None:
        return False
    return restconf_port(device) is not None


def blank_device(name, platform, at, status, error, interfaces, neighbors):
    interfaces = apply_keys(name, interfaces or [])
    return {
        "name": name,
        "platform": platform,
        "status": status,
        "error": error,
        "collected_at": at,
        "interfaces": interfaces,
        "neighbors": neighbors or [],
        "keys": row_keys(name, interfaces),
    }


def read_iosxe(host, port):
    data, err = ios_get(host, port, "Cisco-IOS-XE-native:native/interface", IOS_FIELDS)
    if err:
        data, err = ios_get(host, port, "Cisco-IOS-XE-native:native/interface", IOS_FIELDS_NARROW)
    if err or data is None:
        return None, None, err or "interface list was empty"
    interfaces = parse_ios_interfaces(data)
    cdp, cdp_err = ios_get(host, port, "Cisco-IOS-XE-cdp-oper:cdp-neighbor-details", CDP_FIELDS)
    if cdp_err:
        return interfaces, [], cdp_err
    return interfaces, parse_cdp(cdp), None


def read_ftd(host, port):
    physical, err = ftd_items(host, port, "devices/default/interfaces")
    if err:
        return None, err
    zones_raw, zone_err = ftd_items(host, port, "object/securityzones")
    zones, by_hardware = ([], {}) if zone_err else parse_zones(zones_raw)
    interfaces = []
    sub_err = None
    for item in physical:
        row = parse_ftd_interface(item, None, by_hardware)
        if row:
            interfaces.append(row)
        parent_id = item.get("id")
        hardware = label_text(item.get("hardwareName"))
        if not isinstance(parent_id, str) or SAFE_ID.fullmatch(parent_id) is None:
            continue
        children, child_err = ftd_items(
            host, port, f"devices/default/interfaces/{parent_id}/subinterfaces"
        )
        if child_err:
            if "not found" not in child_err.lower() and "404" not in child_err:
                sub_err = child_err
            continue
        for child in children:
            child_row = parse_ftd_interface(child, hardware, by_hardware)
            if child_row:
                interfaces.append(child_row)
    objects, object_err = ftd_items(host, port, "object/networks")
    policies_raw, policy_err = ftd_items(host, port, "policy/accesspolicies")
    policies = []
    rules = []
    rule_err = None
    if not policy_err:
        for policy in policies_raw:
            policy_name = label_text(policy.get("name"))
            if policy_name is None:
                continue
            action = policy.get("defaultAction")
            default_action = label_text(action.get("action")) if isinstance(action, dict) else None
            policies.append({"name": policy_name, "default_action": default_action})
            policy_id = policy.get("id")
            if not isinstance(policy_id, str) or SAFE_ID.fullmatch(policy_id) is None:
                rule_err = "access policy id was not usable"
                continue
            rule_items, one_err = ftd_items(
                host, port, f"policy/accesspolicies/{policy_id}/accessrules"
            )
            if one_err:
                rule_err = one_err
                continue
            rules.extend(parse_rules(policy_name, rule_items))
    section_errors = {}
    if zone_err:
        section_errors["zones"] = zone_err
    if sub_err:
        section_errors["subinterfaces"] = sub_err
    if object_err:
        section_errors["objects"] = object_err
    if policy_err:
        section_errors["policies"] = policy_err
    if rule_err:
        section_errors["rules"] = rule_err
    firewall = {
        "policies": policies,
        "zones": zones,
        "objects": [] if object_err else parse_objects(objects or []),
        "rules": rules,
    }
    return {"interfaces": interfaces, "firewall": firewall, "section_errors": section_errors}, None


def frozen(rows):
    return tuple(sorted(rows, key=lambda item: tuple("" if part is None else str(part) for part in item)))


def signature(device_row, firewall):
    interfaces = frozen(
        (row.get("hardware") or row["name"], row.get("cidr"), row.get("zone"), row.get("parent"), row.get("vlan"))
        for row in device_row.get("interfaces") or []
    )
    neighbors = frozen(
        (row["local_interface"], row["device"], row.get("port"), row.get("address"))
        for row in device_row.get("neighbors") or []
    )
    rules = ()
    objects = ()
    zones = ()
    if isinstance(firewall, dict):
        rules = frozen(
            (
                row["name"], row["action"], row.get("policy"),
                tuple(row.get("source_zones") or []), tuple(row.get("destination_zones") or []),
                tuple(row.get("source_networks") or []), tuple(row.get("destination_networks") or []),
            )
            for row in firewall.get("rules") or []
        )
        objects = frozen(
            (row["name"], row.get("kind"), row.get("value"))
            for row in firewall.get("objects") or []
        )
        zones = frozen(
            (row["name"], tuple(row.get("interfaces") or []))
            for row in firewall.get("zones") or []
        )
    return (device_row.get("status"), interfaces, neighbors, zones, objects, rules)


def diff_device(name, before, after, at, changes):
    key = [f"device:{name}"]
    if before is None:
        changes.append({"keys": key, "field": "row", "prior": None, "current": name, "at": at})
        return
    if after is None:
        changes.append({"keys": key, "field": "row", "prior": name, "current": None, "at": at})
        return
    if before[0] != after[0]:
        changes.append({"keys": key, "field": "status", "prior": before[0], "current": after[0], "at": at})
    prior_ifaces = {item[0]: item for item in before[1]}
    current_ifaces = {item[0]: item for item in after[1]}
    for label in sorted(set(prior_ifaces) | set(current_ifaces)):
        old = prior_ifaces.get(label)
        new = current_ifaces.get(label)
        if old == new or len(changes) >= 40:
            continue
        old_cidr = None if old is None else old[1]
        new_cidr = None if new is None else new[1]
        old_zone = None if old is None else old[2]
        new_zone = None if new is None else new[2]
        field = "cidr" if old_cidr != new_cidr else "zone" if old_zone != new_zone else "interface"
        changes.append({
            "keys": [f"interface:{name}/{label}"],
            "field": field,
            "prior": old_cidr if field == "cidr" else old_zone,
            "current": new_cidr if field == "cidr" else new_zone,
            "at": at,
        })
    if before[2] != after[2] and len(changes) < 40:
        changes.append({"keys": key, "field": "neighbors", "prior": len(before[2]), "current": len(after[2]), "at": at})
    if before[3] != after[3] and len(changes) < 40:
        changes.append({"keys": key, "field": "zones", "prior": len(before[3]), "current": len(after[3]), "at": at})
    if before[4] != after[4] and len(changes) < 40:
        changes.append({"keys": key, "field": "objects", "prior": len(before[4]), "current": len(after[4]), "at": at})
    if before[5] != after[5] and len(changes) < 40:
        changes.append({"keys": key, "field": "rules", "prior": len(before[5]), "current": len(after[5]), "at": at})


def coverage_for(selected, rows, remaining):
    read = sum(1 for row in rows if row["status"] in {"complete", "partial"})
    failed = sum(1 for row in rows if row["status"] == "unavailable")
    addressed = sum(1 for row in rows for item in row["interfaces"] if item.get("cidr"))
    interfaces = sum(len(row["interfaces"]) for row in rows)
    neighbors = sum(len(row["neighbors"]) for row in rows)
    if not selected:
        state = "unavailable"
    elif read == 0:
        state = "unavailable"
    elif failed or remaining or any(row["status"] != "complete" for row in rows):
        state = "partial"
    else:
        state = "complete"
    return {
        "state": state,
        "selected": len(selected),
        "read": read,
        "failed": failed,
        "remaining": remaining,
        "interfaces": interfaces,
        "interfaces_with_address": addressed,
        "neighbors": neighbors,
    }


def finish(payload, code):
    print(visit_common.summary(payload))
    return code


def cmd_collect(args):
    host = (args.host or "").strip() or None
    if host and (any(char.isspace() for char in host) or "://" in host):
        print('{"error": "host is not a name"}', file=sys.stderr)
        return 1
    ws = resolve_workspace(args.workspace)
    if ws is None:
        return 1
    snapshot = visit_common.load_json(ws, "inventory/network.json")
    if not isinstance(snapshot, dict) or not snapshot.get("lab_title"):
        print('{"error": "inventory/network.json is missing"}', file=sys.stderr)
        return 1
    devices = [item for item in snapshot.get("devices") or [] if isinstance(item, dict) and item.get("name")]
    names = [item["name"] for item in devices]
    if len(names) != len(set(names)):
        print('{"error": "snapshot has two devices with the same name"}', file=sys.stderr)
        return 1
    by_name = {item["name"]: item for item in devices}
    if args.device:
        chosen = by_name.get(args.device)
        if chosen is None:
            print('{"error": "named device is not in the snapshot"}', file=sys.stderr)
            return 1
        if chosen.get("platform") not in {"iosxe", "ftd"}:
            print('{"error": "this visit reads iosxe and ftd only"}', file=sys.stderr)
            return 1
        if restconf_port(chosen) is None:
            print('{"error": "forwarded port is missing"}', file=sys.stderr)
            return 1
        selected = [chosen]
    else:
        selected = [item for item in devices if selectable(item)]
    now = datetime.now(timezone.utc)
    at = checked_at(now)
    prior = visit_common.load_json(ws, CURRENT)
    prior_rows = {}
    if isinstance(prior, dict):
        for row in prior.get("devices") or []:
            if isinstance(row, dict) and row.get("name"):
                prior_rows[row["name"]] = row
    prior_firewalls = {}
    for name in prior_rows:
        rel = firewall_rel(name)
        if rel is None:
            continue
        doc = visit_common.load_json(ws, rel)
        if isinstance(doc, dict):
            prior_firewalls[name] = doc
    prior_sigs = {
        name: signature(row, prior_firewalls.get(name))
        for name, row in prior_rows.items()
    }
    if not selected:
        print(visit_common.summary({
            "visit": "devices",
            "lab_title": snapshot.get("lab_title"),
            "status": "unavailable",
            "selected": 0,
            "read": 0,
            "failed": 0,
            "remaining": 0,
            "interfaces": 0,
            "interfaces_with_address": 0,
            "neighbors": 0,
            "firewalls": 0,
            "rules": 0,
            "stamp": None,
            "wrote": [],
            "error": "no iosxe or ftd device has a forwarded port",
        }))
        return 0
    deadline = time.monotonic() + BUDGET_SECONDS
    collected = {}
    firewalls = {}
    remaining = 0
    for index, device in enumerate(selected):
        if time.monotonic() >= deadline:
            remaining = len(selected) - index
            break
        name = device["name"]
        platform = device["platform"]
        port = restconf_port(device)
        prior_row = prior_rows.get(name)
        if platform == "iosxe":
            interfaces, neighbors, err = read_iosxe(host, port)
            if interfaces is None:
                collected[name] = blank_device(
                    name, platform, at, "unavailable", err,
                    (prior_row or {}).get("interfaces"), (prior_row or {}).get("neighbors"),
                )
                continue
            status = "partial" if err else "complete"
            collected[name] = blank_device(name, platform, at, status, err, interfaces, neighbors)
            continue
        result, err = read_ftd(host, port)
        if result is None:
            collected[name] = blank_device(
                name, platform, at, "unavailable", err,
                (prior_row or {}).get("interfaces"), [],
            )
            continue
        section_errors = result["section_errors"]
        prior_fw = prior_firewalls.get(name)
        firewall = result["firewall"]
        if isinstance(prior_fw, dict):
            for section in ("zones", "objects", "rules", "policies"):
                if section in section_errors:
                    firewall[section] = prior_fw.get(section) or []
            if "policies" in section_errors:
                firewall["rules"] = prior_fw.get("rules") or []
        if "zones" in section_errors and prior_row:
            previous = {
                (item.get("hardware") or item.get("name")): item.get("zone")
                for item in prior_row.get("interfaces") or []
                if isinstance(item, dict)
            }
            for item in result["interfaces"]:
                label = item.get("hardware") or item.get("name")
                if previous.get(label):
                    item["zone"] = previous[label]
        status = "partial" if section_errors else "complete"
        error = "; ".join(section_errors.values())[:200] if section_errors else None
        collected[name] = blank_device(
            name, platform, at, status, error, result["interfaces"], [],
        )
        rel = firewall_rel(name)
        if rel is None:
            collected[name]["status"] = "partial"
            collected[name]["error"] = "device name is not a safe file name"
            continue
        fw_doc = {
            "schema": "network-firewall/v1",
            "device": name,
            "collected_at": at,
            "source_agent": "device-discovery",
            "status": "partial" if error else "complete",
            "policies": firewall["policies"],
            "zones": firewall["zones"],
            "objects": firewall["objects"],
            "rules": firewall["rules"],
            "keys": collected[name]["keys"],
        }
        try:
            validate(fw_doc, "network-firewall.schema.json")
        except Exception as exc:
            collected[name]["status"] = "partial"
            collected[name]["error"] = f"firewall file invalid: {exc.__class__.__name__}"
            continue
        visit_common.save_json(ws, rel, fw_doc)
        firewalls[name] = fw_doc
    if args.device:
        merged = []
        seen = set()
        for row in list(prior_rows.values()):
            if row["name"] == args.device:
                continue
            merged.append(row)
            seen.add(row["name"])
        if args.device in collected:
            merged.append(collected[args.device])
        merged.sort(key=lambda row: row["name"])
    else:
        merged = []
        for device in devices:
            if device["name"] in collected:
                merged.append(collected[device["name"]])
            elif device["name"] in prior_rows and not selectable(device):
                continue
            elif device["name"] in prior_rows and remaining and device["name"] not in collected:
                merged.append(prior_rows[device["name"]])
        for name, row in collected.items():
            if name not in {item["name"] for item in merged}:
                merged.append(row)
        merged.sort(key=lambda row: row["name"])
    touched = [collected[name] for name in collected]
    cover = coverage_for(selected, touched, remaining)
    rules = sum(len(doc.get("rules") or []) for doc in firewalls.values())
    headline = (
        f"{cover['read']} devices answered, {cover['interfaces_with_address']} addressed interfaces, "
        f"{cover['neighbors']} neighbors."
    )
    if cover["state"] == "complete":
        next_action = "Caldera can read interface addresses, neighbors, and firewall rules."
    elif remaining:
        next_action = "Run the visit again to read the remaining devices."
    elif cover["failed"]:
        next_action = "Some devices did not answer. Rows that answered are current."
    else:
        next_action = "Some device facts are incomplete."
    keys = []
    for row in merged:
        keys.extend(row.get("keys") or [])
    keys = list(dict.fromkeys(keys))
    current = {
        "schema": "network-endpoints/v1",
        "lab_title": snapshot.get("lab_title"),
        "lab_id": snapshot.get("lab_id") or "",
        "collected_at": at,
        "source_agent": "device-discovery",
        "status": cover["state"],
        "headline": headline,
        "next_action": next_action,
        "coverage": {
            "state": cover["state"],
            "selected": cover["selected"],
            "read": cover["read"],
            "failed": cover["failed"],
            "remaining": cover["remaining"],
            "interfaces": cover["interfaces"],
            "interfaces_with_address": cover["interfaces_with_address"],
            "neighbors": cover["neighbors"],
            "firewalls": len(firewalls),
            "rules": rules,
        },
        "devices": merged,
        "keys": keys,
    }
    try:
        validate(current, "network-endpoints.schema.json")
    except Exception as exc:
        print(f'{{"error": "endpoints file invalid: {exc.__class__.__name__}"}}', file=sys.stderr)
        return 1
    visit_common.save_json(ws, CURRENT, current)
    changes = []
    current_sigs = {}
    for row in merged:
        fw = firewalls.get(row["name"]) or prior_firewalls.get(row["name"])
        current_sigs[row["name"]] = signature(row, fw)
    compared = set(collected)
    if not args.device:
        compared |= {name for name in prior_sigs if name not in current_sigs}
    for name in sorted(compared):
        diff_device(name, prior_sigs.get(name), current_sigs.get(name), at, changes)
    first = not isinstance(prior, dict)
    write_stamp = first or bool(changes)
    stamp_id = None
    wrote = [CURRENT]
    wrote.extend(firewall_rel(name) for name in sorted(firewalls))
    if write_stamp:
        stamp_id = fresh_stamp_id(ws, now)
        visit = {
            "schema": "network-endpoints-visit/v1",
            "visit_id": stamp_id,
            "checked_at": at,
            "source_agent": "device-discovery",
            "lab_title": snapshot.get("lab_title"),
            "status": cover["state"],
            "headline": headline if first else "Interface addresses, neighbors, or firewall rules changed.",
            "coverage": current["coverage"],
            "vs_prior": {"changed": changes},
            "keys": keys,
        }
        validate(visit, "network-endpoints-visit.schema.json")
        visit_common.save_json(ws, f"network/endpoints/{stamp_id}.json", visit)
        prune_stamps(ws)
        wrote.append(f"network/endpoints/{stamp_id}.json")
    prior_board = visit_common.load_json(ws, METADATA) or {}
    visits = list(prior_board.get("visits") or [])
    visits.append({
        "watch_id": stamp_id,
        "checked_at": at,
        "status": cover["state"],
        "delta": len(changes),
        "stamp_written": stamp_id is not None,
    })
    board = {
        "schema": "network-endpoints-metadata/v1",
        "lab_title": snapshot.get("lab_title"),
        "source_agent": "device-discovery",
        "last_visit_id": stamp_id if stamp_id else prior_board.get("last_visit_id"),
        "last_collected_at": at,
        "coverage": current["coverage"],
        "visits": visits[-10:],
        "keys": keys,
    }
    validate(board, "network-endpoints-metadata.schema.json")
    visit_common.save_json(ws, METADATA, board)
    wrote.append(METADATA)
    return finish({
        "visit": "devices",
        "lab_title": snapshot.get("lab_title"),
        "status": cover["state"],
        "selected": cover["selected"],
        "read": cover["read"],
        "failed": cover["failed"],
        "remaining": cover["remaining"],
        "interfaces": cover["interfaces"],
        "interfaces_with_address": cover["interfaces_with_address"],
        "neighbors": cover["neighbors"],
        "firewalls": len(firewalls),
        "rules": rules,
        "stamp": stamp_id,
        "wrote": wrote,
    }, 0)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--workspace", required=True)
    collect.add_argument("--host", default=None)
    collect.add_argument("--device", default=None)
    args = parser.parse_args()
    if args.command == "collect":
        try:
            return cmd_collect(args)
        except Exception as exc:
            print(f'{{"error": "{exc.__class__.__name__}"}}', file=sys.stderr)
            return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
