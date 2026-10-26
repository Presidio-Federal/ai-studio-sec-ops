#!/usr/bin/env python3
"""CML network visit.

collect runs under execution_type mcp_orchestration. The script calls
CML, reduces the payload, and writes the network directory. Node
configuration text is parsed for interface addresses and discarded.
It is never written to the workspace or stdout.

  python3 <skill>/scripts/visit_network.py collect --workspace <file_explorer> --lab "<title>"
"""
import argparse
import json
import re
import sys
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

IFACE = re.compile(r"^interface\s+(\S+)", re.I)
IP_MASK = re.compile(
    r"^\s*(?:ip|ipv4) address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\b",
    re.I,
)
IP_PREFIX = re.compile(
    r"^\s*(?:ip|ipv4) address\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\b",
    re.I,
)
PAT = re.compile(r"^pat:(\d+):(\d+)$")
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def parse_interface_addresses(config):
    """Map an interface name to a CIDR. Ignores every other line."""
    if not isinstance(config, str) or not config.strip():
        return {}
    found = {}
    current = None
    for line in config.splitlines():
        match = IFACE.match(line)
        if match:
            current = match.group(1)
            continue
        if current is None:
            continue
        if line.startswith("!") or (line[:1].strip() and not line.lower().startswith("interface ")):
            current = None
            continue
        if re.match(r"^\s*no (?:ip|ipv4) address\b", line, re.I):
            continue
        if re.search(r"\b(dhcp|secondary)\b", line, re.I):
            continue
        prefixed = IP_PREFIX.match(line)
        if prefixed:
            found.setdefault(current, f"{prefixed.group(1)}/{int(prefixed.group(2))}")
            continue
        masked = IP_MASK.match(line)
        if not masked:
            continue
        prefix = mask_to_prefix(masked.group(2))
        if prefix is None:
            continue
        found.setdefault(current, f"{masked.group(1)}/{prefix}")
    return found


def mask_to_prefix(mask):
    try:
        parts = [int(part) for part in mask.split(".")]
    except ValueError:
        return None
    if len(parts) != 4 or any(part < 0 or part > 255 for part in parts):
        return None
    bits = "".join(f"{part:08b}" for part in parts)
    if "01" in bits:
        return None
    return bits.count("1")


def resolve_workspace(given):
    """Directory the agent copied. Prefer one that already holds the snapshot."""
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
            print(f"network workspace={resolved}", file=sys.stderr)
            return resolved
        if resolved.is_dir():
            existing.append(resolved)
    if existing:
        print(f"network workspace={existing[0]}", file=sys.stderr)
        return existing[0]
    print('{"error": "workspace directory missing"}', file=sys.stderr)
    print("tried " + ", ".join(str(path) for path in seen), file=sys.stderr)
    return None


def checked_at(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh_stamp_id(ws, moment):
    folder = Path(ws) / "network"
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        name = moment.strftime("%Y-%m-%dT%H-%M-%SZ")
        if not (folder / f"{name}.json").exists():
            return name
        moment = moment + timedelta(seconds=1)


def prune_stamps(ws):
    folder = Path(ws) / "network"
    if not folder.is_dir():
        return
    stamps = sorted(
        path for path in folder.glob("*.json")
        if path.is_file() and path.name != "metadata.json"
    )
    for path in stamps[:-10]:
        path.unlink()


def validate(instance, schema_name):
    import jsonschema

    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(instance)


def forwarded_from_tags(tags):
    forwarded = []
    kept = []
    group = None
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        if tag.startswith("group:") and group is None and tag.split(":", 1)[1].strip():
            group = tag.split(":", 1)[1].strip()
            kept.append(tag)
            continue
        match = PAT.match(tag)
        if match:
            forwarded.append({
                "external_port": int(match.group(1)),
                "internal_port": int(match.group(2)),
            })
            continue
        if not tag.startswith("pat:"):
            kept.append(tag)
    forwarded.sort(key=lambda item: (item["external_port"], item["internal_port"]))
    return forwarded, kept, group


def access_from_forwarded(forwarded):
    def one(internal):
        matches = [item for item in forwarded if item["internal_port"] == internal]
        if len(matches) != 1:
            return None
        return {"port": matches[0]["external_port"], "internal_port": internal}

    return {"restconf": one(443), "ssh": one(22)}


def interface_rows(node, addresses):
    rows = []
    seen = set()
    for iface in node.get("interfaces") or []:
        if not isinstance(iface, dict):
            continue
        name = iface.get("label")
        if not isinstance(name, str) or not name.strip():
            continue
        cidr = addresses.pop(name, None)
        if cidr is None and iface.get("ip_address"):
            cidr = str(iface["ip_address"])
        rows.append({"name": name, "cidr": cidr})
        seen.add(name)
    for name in sorted(addresses):
        if name not in seen:
            rows.append({"name": name, "cidr": addresses[name]})
    rows.sort(key=lambda item: item["name"])
    return rows


def platform_for(node_definition):
    """Classify a CML node definition. Unknown types keep the source string."""
    name = (node_definition or "").strip().lower()
    if name in {"cat8000v", "iosv", "csr1000v", "iosvl2"}:
        return "iosxe"
    if name in {"nxosv", "nxosv9000"}:
        return "nxos"
    if name in {"asav"}:
        return "asa"
    if name in {"ftdv"}:
        return "ftd"
    if name in {"ubuntu", "alpine", "server"}:
        return "linux"
    return node_definition or ""


def device_from_node(node):
    tags = list(node.get("tags") or [])
    forwarded, kept, group = forwarded_from_tags(tags)
    running = node.get("running_config") if isinstance(node.get("running_config"), str) else ""
    bootstrap = node.get("bootstrap_config") if isinstance(node.get("bootstrap_config"), str) else ""
    addresses = parse_interface_addresses(bootstrap)
    addresses.update(parse_interface_addresses(running))
    interfaces = interface_rows(node, addresses)
    name = node.get("label") or ""
    keys = [f"device:{name}"] if name else []
    keys.extend(f"interface:{name}/{row['name']}" for row in interfaces if name and row["name"])
    access = access_from_forwarded(forwarded)
    return {
        "id": node.get("id") or "",
        "name": name,
        "node_definition": node.get("node_definition") or "",
        "platform": platform_for(node.get("node_definition") or ""),
        "state": node.get("state"),
        "group": group,
        "tags": kept,
        "agent_access": access["restconf"] is not None or access["ssh"] is not None,
        "access": access,
        "forwarded": forwarded,
        "interfaces": interfaces,
        "keys": keys,
    }


def links_from_lab(lab, devices):
    by_iface = {}
    for node in lab.get("nodes") or []:
        label = node.get("label")
        for iface in node.get("interfaces") or []:
            if isinstance(iface, dict) and iface.get("id") and label and iface.get("label"):
                by_iface[iface["id"]] = (label, iface["label"])
    links = []
    unresolved = 0
    for link in lab.get("links") or []:
        if not isinstance(link, dict):
            continue
        left = by_iface.get(link.get("interface_a"))
        right = by_iface.get(link.get("interface_b"))
        if not left or not right:
            unresolved += 1
            continue
        links.append({
            "a_device": left[0],
            "a_interface": left[1],
            "b_device": right[0],
            "b_interface": right[1],
        })
    known = {device["name"] for device in devices}
    links = [
        link for link in links
        if link["a_device"] in known and link["b_device"] in known
    ]
    links.sort(key=lambda item: (item["a_device"], item["a_interface"], item["b_device"], item["b_interface"]))
    return links, unresolved


def device_view(device):
    return {
        "forwarded": [(item["external_port"], item["internal_port"]) for item in device["forwarded"]],
        "interfaces": [(item["name"], item.get("cidr")) for item in device["interfaces"]],
    }


def link_view(link):
    return tuple(sorted([
        (link["a_device"], link["a_interface"]),
        (link["b_device"], link["b_interface"]),
    ]))


def diff_network(prior, current, at):
    if not isinstance(prior, dict):
        prior = {"devices": [], "links": []}
    changes = []
    prior_devices = {device["name"]: device for device in prior.get("devices") or [] if device.get("name")}
    current_devices = {device["name"]: device for device in current.get("devices") or [] if device.get("name")}
    for name in sorted(set(prior_devices) | set(current_devices)):
        before = prior_devices.get(name)
        after = current_devices.get(name)
        key = [f"device:{name}"]
        if before is None:
            changes.append({"keys": key, "field": "row", "prior": None, "current": name, "at": at})
            continue
        if after is None:
            changes.append({"keys": key, "field": "row", "prior": name, "current": None, "at": at})
            continue
        left = device_view(before)
        right = device_view(after)
        if before.get("platform") != after.get("platform"):
            changes.append({
                "keys": key,
                "field": "platform",
                "prior": before.get("platform"),
                "current": after.get("platform"),
                "at": at,
            })
        if left["forwarded"] != right["forwarded"]:
            changes.append({
                "keys": key,
                "field": "forwarded",
                "prior": before["forwarded"],
                "current": after["forwarded"],
                "at": at,
            })
        if left["interfaces"] != right["interfaces"]:
            changes.append({
                "keys": after["keys"],
                "field": "interfaces",
                "prior": before["interfaces"],
                "current": after["interfaces"],
                "at": at,
            })
    prior_links = {link_view(link) for link in prior.get("links") or []}
    current_links = {link_view(link) for link in current.get("links") or []}
    for view in sorted(prior_links - current_links):
        changes.append({
            "keys": [f"device:{end[0]}" for end in view],
            "field": "link",
            "prior": [{"device": end[0], "interface": end[1]} for end in view],
            "current": None,
            "at": at,
        })
    for view in sorted(current_links - prior_links):
        changes.append({
            "keys": [f"device:{end[0]}" for end in view],
            "field": "link",
            "prior": None,
            "current": [{"device": end[0], "interface": end[1]} for end in view],
            "at": at,
        })
    return changes


def coverage_for(devices, links, unresolved):
    interfaces = [row for device in devices for row in device["interfaces"]]
    forwarded = [item for device in devices for item in device["forwarded"]]
    state = "complete"
    if unresolved:
        state = "partial"
    if not devices:
        state = "unavailable"
    return {
        "state": state,
        "devices": len(devices),
        "links": len(links),
        "forwarded": len(forwarded),
        "interfaces": len(interfaces),
        "interfaces_with_address": sum(1 for row in interfaces if row.get("cidr")),
        "unresolved_links": unresolved,
    }


def union_keys(devices):
    keys = []
    seen = set()
    for device in devices:
        for key in device.get("keys") or []:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def fail(ws, lab_title, message, now):
    at = checked_at(now)
    prior = visit_common.load_json(ws, "network/metadata.json") if ws else None
    visits = list((prior or {}).get("visits") or [])
    visits.append({
        "watch_id": None,
        "checked_at": at,
        "status": "unavailable",
        "delta": 0,
        "stamp_written": False,
    })
    board = {
        "schema": "network-metadata/v1",
        "lab_title": (prior or {}).get("lab_title") or lab_title or None,
        "source_agent": "network-discovery",
        "last_visit_id": None if prior is None else prior.get("last_visit_id"),
        "last_collected_at": at,
        "coverage": {"state": "unavailable"},
        "visits": visits[-10:],
        "keys": [] if prior is None else list(prior.get("keys") or []),
    }
    wrote = []
    if ws is not None:
        visit_common.save_json(ws, "network/metadata.json", board)
        wrote.append("network/metadata.json")
    print(message, file=sys.stderr)
    print(visit_common.summary({
        "visit": "network",
        "lab_title": lab_title,
        "status": "unavailable",
        "devices": 0,
        "links": 0,
        "forwarded": 0,
        "interfaces": 0,
        "interfaces_with_address": 0,
        "stamp": None,
        "wrote": wrote,
        "error": message,
    }))
    return 1


def merge_tags(lab):
    """Confirm tags with node info when lab details carried none."""
    nodes = [node for node in lab.get("nodes") or [] if isinstance(node, dict)]
    if any(any(isinstance(tag, str) and tag.startswith("pat:") for tag in (node.get("tags") or [])) for node in nodes):
        return None
    ids = [node.get("id") for node in nodes if node.get("id")]
    if not ids:
        return None
    body, err = visit_common.tool_body(visit_common.mcp_call("cml_get_node_info", {
        "lab_id": lab.get("lab_id") or "",
        "node_ids": json.dumps(ids),
        "include_configuration": False,
        "include_interfaces": False,
        "include_peers": False,
    }))
    if err:
        return err
    by_id = {}
    for node in body.get("nodes") or []:
        if isinstance(node, dict) and node.get("id"):
            by_id[node["id"]] = node.get("tags") or []
    for node in nodes:
        if node.get("id") in by_id and not node.get("tags"):
            node["tags"] = by_id[node["id"]]
    return None


def cmd_collect(args):
    title = (args.lab or "").strip()
    ws = resolve_workspace(args.workspace)
    now = datetime.now(timezone.utc)
    if not title:
        return fail(ws, "", "lab title missing", now)
    if ws is None:
        return 1
    listed, err = visit_common.tool_body(visit_common.mcp_call("cml_list_labs", {}))
    if err:
        return fail(ws, title, err, now)
    matches = [
        lab for lab in (listed.get("labs") or [])
        if isinstance(lab, dict) and lab.get("title") == title
    ]
    if len(matches) != 1 or not matches[0].get("id"):
        reason = "lab title matched more than one lab" if len(matches) > 1 else "lab title not in cml_list_labs"
        return fail(ws, title, reason, now)
    lab_id = matches[0]["id"]
    detailed, err = visit_common.tool_body(visit_common.mcp_call("cml_get_lab_details", {
        "lab_id": lab_id,
        "include_configurations": True,
    }))
    if err:
        detailed, err = visit_common.tool_body(visit_common.mcp_call("cml_get_lab_details", {
            "lab_id": lab_id,
            "include_configurations": False,
        }))
    if err:
        return fail(ws, title, err, now)
    tag_err = merge_tags(detailed)
    if tag_err:
        return fail(ws, title, tag_err, now)
    devices = [device_from_node(node) for node in detailed.get("nodes") or [] if isinstance(node, dict)]
    devices = [device for device in devices if device["name"]]
    devices.sort(key=lambda item: item["name"])
    if not devices:
        return fail(ws, title, "lab details returned no nodes", now)
    links, unresolved = links_from_lab(detailed, devices)
    # Configuration strings are local variables on the tool payload and are not copied.
    detailed.pop("nodes", None)
    cover = coverage_for(devices, links, unresolved)
    at = checked_at(now)
    keys = union_keys(devices)
    headline = (
        f"{title}: {cover['devices']} devices, {cover['links']} links, "
        f"{cover['forwarded']} forwarded ports."
    )
    next_action = "none" if cover["interfaces"] == cover["interfaces_with_address"] else "Interface addresses are incomplete."
    snapshot = {
        "schema": "network-inventory/v1",
        "lab_title": detailed.get("lab_title") or title,
        "lab_id": detailed.get("lab_id") or lab_id,
        "collected_at": at,
        "source_agent": "network-discovery",
        "status": cover["state"],
        "headline": headline,
        "next_action": next_action,
        "coverage": cover,
        "devices": devices,
        "links": links,
        "services": [],
        "keys": keys,
    }
    prior = visit_common.load_json(ws, "inventory/network.json")
    changes = diff_network(prior, snapshot, at)
    first = not isinstance(prior, dict)
    write_stamp = first or bool(changes)
    prior_board = visit_common.load_json(ws, "network/metadata.json") or {}
    stamp_id = None
    if write_stamp:
        stamp_id = fresh_stamp_id(ws, now)
        visit = {
            "schema": "network-visit/v1",
            "visit_id": stamp_id,
            "checked_at": at,
            "source_agent": "network-discovery",
            "lab_title": snapshot["lab_title"],
            "status": cover["state"],
            "headline": headline if first else "Forwarded ports, interfaces, or links changed.",
            "coverage": cover,
            "vs_prior": {"changed": changes},
            "keys": keys,
        }
        validate(visit, "network-visit.schema.json")
        visit_common.save_json(ws, f"network/{stamp_id}.json", visit)
        prune_stamps(ws)
    validate(snapshot, "network-inventory.schema.json")
    visit_common.save_json(ws, "inventory/network.json", snapshot)
    visits = list(prior_board.get("visits") or [])
    visits.append({
        "watch_id": stamp_id,
        "checked_at": at,
        "status": cover["state"],
        "delta": len(changes),
        "stamp_written": stamp_id is not None,
    })
    board = {
        "schema": "network-metadata/v1",
        "lab_title": snapshot["lab_title"],
        "source_agent": "network-discovery",
        "last_visit_id": stamp_id if stamp_id else prior_board.get("last_visit_id"),
        "last_collected_at": at,
        "coverage": cover,
        "visits": visits[-10:],
        "keys": keys,
    }
    validate(board, "network-metadata.schema.json")
    visit_common.save_json(ws, "network/metadata.json", board)
    wrote = ["inventory/network.json", "network/metadata.json"]
    if stamp_id:
        wrote.append(f"network/{stamp_id}.json")
    print(visit_common.summary({
        "visit": "network",
        "lab_title": snapshot["lab_title"],
        "status": cover["state"],
        "devices": cover["devices"],
        "links": cover["links"],
        "forwarded": cover["forwarded"],
        "interfaces": cover["interfaces"],
        "interfaces_with_address": cover["interfaces_with_address"],
        "stamp": stamp_id,
        "wrote": wrote,
    }))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--workspace", required=True)
    collect.add_argument("--lab", required=True)
    args = parser.parse_args()
    if args.command == "collect":
        return cmd_collect(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
