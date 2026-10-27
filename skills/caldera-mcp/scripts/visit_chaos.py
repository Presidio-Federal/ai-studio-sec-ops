#!/usr/bin/env python3
"""Caldera campaign visit.

collect and run execute under execution_type mcp_orchestration.
The script calls Caldera, reduces the payload, and writes the chart.
Commands are never written.

  python3 <skill>/scripts/visit_chaos.py collect --workspace <file_explorer>
  python3 <skill>/scripts/visit_chaos.py run --workspace <file_explorer> --goal chaos
"""
import argparse
import ipaddress
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

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
WORD = re.compile(r"[a-z]+")
KIND_ORDER = ("scan", "traffic", "application")
FORBIDDEN_TACTICS = {
    "exfiltration",
    "lateral-movement",
    "impact",
    "credential-access",
    "defense-evasion",
}
GOAL_KIND = {
    "chaos": ("scan",),
    "traffic": ("traffic",),
    "scan": ("scan",),
    "application": ("application",),
}


def checked_at(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def tokens(name):
    found = set()
    for word in WORD.findall((name or "").lower()):
        if word in {"app", "apps", "application", "applications"}:
            found.add("app")
        elif word != "lab":
            found.add(word)
    return found


def classify(name, description, ability_names):
    blob = " ".join([name or "", description or "", *ability_names]).lower()
    if any(word in blob for word in ("dscp", "tos", "marked", "syn")):
        return "traffic"
    if "scan" in blob or "port" in blob:
        return "scan"
    if any(word in blob for word in ("application", "http", "url")):
        return "application"
    return None


def why_for(name, on_lab):
    low = (name or "").lower()
    for word in ("scan", "probe", "sweep", "port"):
        if word in low:
            return word
    if on_lab:
        return "lab-adversary"
    return None


def fresh(value, now):
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip().replace("Z", "+00:00")
    try:
        seen = datetime.fromisoformat(text)
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return now - seen <= timedelta(hours=2)


def ability_ids(adversary):
    found = []
    for step in adversary.get("atomic_ordering") or []:
        if isinstance(step, str):
            found.append(step)
        elif isinstance(step, dict):
            ability_id = step.get("ability_id") or step.get("id")
            if isinstance(ability_id, str):
                found.append(ability_id)
    return found


def device_key(host):
    if isinstance(host, str) and host.strip() and " " not in host:
        return f"device:{host.strip()}"
    return None


def strip_arg(value):
    return str(value or "").strip().strip("'\"")


def resolve_workspace(given):
    """Same rule as health-logging: the directory that holds the catalog anchor."""
    raw = Path(strip_arg(given))
    candidates = [raw]
    if not raw.is_absolute():
        candidates.append(Path.cwd() / raw)
        candidates.append(Path.cwd())
    candidates.append(Path(__file__).resolve().parents[3] / "file_explorer")
    seen = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.append(resolved)
        if (resolved / "inventory" / "network.json").is_file():
            print(f"chaos workspace={resolved}", file=sys.stderr)
            return resolved
    print('{"error": "inventory/network.json missing"}', file=sys.stderr)
    print("tried " + ", ".join(str(path) for path in seen), file=sys.stderr)
    return None


def validate(instance, schema_name):
    import jsonschema

    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(instance)


def save(ws, rel, payload, schema_name):
    validate(payload, schema_name)
    visit_common.save_json(ws, rel, payload)


def get_path(path, include):
    body, err = visit_common.tool_body(visit_common.mcp_call("caldera_get", {
        "path": path,
        "include": include,
    }))
    if err:
        return None, err
    return body.get("data"), None


def as_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "agents", "adversaries", "abilities", "sources", "operations"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def load_caldera():
    status, err = visit_common.tool_body(visit_common.mcp_call("caldera_status", {}))
    if err or not status:
        return None, err or "caldera status failed"
    agents, err = get_path(
        "/api/v2/agents",
        ["paw", "host", "group", "platform", "last_seen", "trusted", "host_ip_addrs"],
    )
    if err:
        return None, err
    adversaries, err = get_path(
        "/api/v2/adversaries",
        ["adversary_id", "name", "description", "atomic_ordering"],
    )
    if err:
        return None, err
    abilities, err = get_path(
        "/api/v2/abilities",
        ["ability_id", "name", "tactic", "technique_id"],
    )
    if err:
        return None, err
    planners, err = get_path("/api/v2/planners", ["id", "name"])
    if err:
        return None, err
    sources, err = get_path("/api/v2/sources", ["id", "name"])
    if err:
        return None, err
    operations, err = get_path(
        "/api/v2/operations/summary",
        ["id", "name", "state", "start", "group", "adversary"],
    )
    if err:
        return None, err
    detailed = []
    for source in as_rows(sources):
        if not isinstance(source, dict) or not str(source.get("name") or "").lower().startswith("lab"):
            continue
        one, err = get_path(f"/api/v2/sources/{source.get('id')}", ["id", "name", "facts"])
        if err or not isinstance(one, dict):
            detailed.append(source)
        else:
            detailed.append(one)
    return {
        "agents": as_rows(agents),
        "adversaries": as_rows(adversaries),
        "abilities": {row.get("ability_id"): row for row in as_rows(abilities) if isinstance(row, dict)},
        "planners": as_rows(planners),
        "sources": detailed,
        "operations": as_rows(operations),
    }, None


def enrolled(agents, now):
    rows = []
    groups = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        if agent.get("trusted") not in (True, 1, "true", "True"):
            continue
        group = agent.get("group") if isinstance(agent.get("group"), str) else ""
        host = agent.get("host") if isinstance(agent.get("host"), str) else ""
        if not group.strip() or not fresh(agent.get("last_seen"), now):
            continue
        addresses = agent.get("host_ip_addrs")
        if isinstance(addresses, str):
            addresses = [addresses]
        if not isinstance(addresses, list):
            addresses = []
        rows.append({
            "paw": str(agent.get("paw") or ""),
            "host": host,
            "group": group.strip(),
            "addresses": [item for item in addresses if isinstance(item, str)],
            "last_seen": agent.get("last_seen"),
            "device": host,
        })
        if group.strip() not in groups:
            groups.append(group.strip())
    return rows, groups


def lab_profiles(bundle):
    profiles = []
    for adversary in bundle["adversaries"]:
        if not isinstance(adversary, dict):
            continue
        name = adversary.get("name") or ""
        if not name.lower().startswith("lab"):
            continue
        ids = ability_ids(adversary)
        names = []
        for ability_id in ids:
            ability = bundle["abilities"].get(ability_id) or {}
            if ability.get("name"):
                names.append(ability["name"])
        kind = classify(name, adversary.get("description"), names)
        adversary_id = adversary.get("adversary_id")
        if kind is None or not isinstance(adversary_id, str) or not adversary_id:
            continue
        profiles.append({
            "adversary_id": adversary_id,
            "name": name,
            "kind": kind,
            "ability_ids": ids,
        })
    profiles.sort(key=lambda row: KIND_ORDER.index(row["kind"]))
    return profiles


def pair_source(profile, sources):
    need = {"traffic": "traffic", "scan": "scan", "application": "app"}[profile["kind"]]
    if need not in tokens(profile["name"]):
        return None
    for source in sources:
        if need in tokens(source.get("name") or ""):
            return source
    return None


def add_net(nets, value):
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    try:
        net = ipaddress.ip_network(text if "/" in text else f"{text}/32", strict=False)
    except ValueError:
        return
    if net not in nets:
        nets.append(net)


def collect_nets(obj, nets):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"cidr", "address", "value"} and isinstance(value, str):
                add_net(nets, value)
            else:
                collect_nets(value, nets)
    elif isinstance(obj, list):
        for item in obj:
            collect_nets(item, nets)


def chart_networks(ws):
    """Addresses already written by the network and device visits."""
    nets = []
    docs = []
    for rel in ("inventory/network.json", "network/endpoints/current.json"):
        doc = visit_common.load_json(ws, rel)
        if isinstance(doc, dict):
            docs.append(doc)
    folder = Path(ws) / "network" / "firewall"
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(doc, dict):
                docs.append(doc)
    for doc in docs:
        collect_nets(doc, nets)
    return nets


def fact_ip(value):
    text = value.strip()
    if "://" in text:
        host = text.split("://", 1)[1].split("/", 1)[0]
        host = host.rsplit("@", 1)[-1]
        if host.startswith("[") and "]" in host:
            host = host[1:host.index("]")]
        elif host.count(":") == 1:
            host = host.split(":", 1)[0]
        text = host
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def on_chart(value, nets):
    ip = fact_ip(value)
    if ip is not None:
        return any(ip in net for net in nets)
    text = value.strip()
    if "://" in text:
        return False
    try:
        fact_net = ipaddress.ip_network(text, strict=False)
    except ValueError:
        return False
    return any(fact_net.overlaps(net) for net in nets)


def usable_facts(source):
    rows = []
    for fact in source.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        trait = fact.get("trait")
        value = fact.get("value")
        if trait in {"app.url", "remote.host.ip"} and isinstance(value, str):
            rows.append({"trait": trait, "value": value})
    return rows


def profile_safe(profile, abilities):
    ids = profile.get("ability_ids") or []
    if not ids:
        return False
    for ability_id in ids:
        tactic = (abilities.get(ability_id) or {}).get("tactic")
        if tactic in FORBIDDEN_TACTICS:
            return False
    return True


def source_matches(source, nets):
    facts = usable_facts(source)
    if not facts or not nets:
        return False
    return all(on_chart(fact["value"], nets) for fact in facts)


def source_facts(sources):
    rows = []
    for source in sources:
        name = source.get("name") or ""
        for fact in source.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            trait = fact.get("trait")
            value = fact.get("value")
            if trait in {"app.url", "remote.host.ip"} and isinstance(value, str):
                rows.append({"source": name, "trait": trait, "value": value})
    return rows


def kept_abilities(bundle, profiles):
    on_lab = set()
    for profile in profiles:
        on_lab.update(profile["ability_ids"])
    rows = []
    for ability_id, ability in bundle["abilities"].items():
        if not isinstance(ability_id, str) or not ability_id:
            continue
        if ability_id not in on_lab:
            continue
        name = ability.get("name") or ""
        why = why_for(name, True)
        if why is None:
            continue
        tactic = ability.get("tactic")
        technique = ability.get("technique_id")
        rows.append({
            "ability_id": ability_id,
            "name": name,
            "tactic": tactic if isinstance(tactic, str) and tactic else "discovery",
            "technique_id": technique if isinstance(technique, str) else None,
            "why": why,
        })
    rows.sort(key=lambda row: row["name"])
    return rows


def running_pairs(operations):
    found = set()
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("state") != "running":
            continue
        group = operation.get("group") or ""
        adversary = operation.get("adversary")
        name = adversary.get("name") if isinstance(adversary, dict) else adversary
        if group and name:
            found.add((group, name))
    return found


def atomic_planner(planners):
    for planner in planners:
        if isinstance(planner, dict) and planner.get("name") == "atomic" and planner.get("id"):
            return planner["id"]
    return None


def link_row(link, abilities):
    if not isinstance(link, dict):
        return None
    ability = link.get("ability")
    name = ""
    technique = None
    if isinstance(ability, dict):
        name = ability.get("name") or ""
        technique = ability.get("technique_id")
    elif isinstance(ability, str):
        known = abilities.get(ability) or {}
        name = known.get("name") or ability
        technique = known.get("technique_id")
    status = link.get("status")
    if isinstance(status, bool) or not isinstance(status, int):
        status = None
    return {
        "host": link.get("host") if isinstance(link.get("host"), str) else None,
        "paw": link.get("paw") if isinstance(link.get("paw"), str) else None,
        "ability": name,
        "technique_id": technique if isinstance(technique, str) else None,
        "status": status,
    }


def create_operation(group, profile, source, planner_id, now):
    payload = {
        "name": f"{group}-{profile['kind']}-{now.strftime('%Y%m%dT%H%MZ')}",
        "group": group,
        "autonomous": 1,
        "planner": {"id": planner_id},
        "adversary": {"adversary_id": profile["adversary_id"]},
        "source": {"id": source.get("id")},
    }
    body, err = visit_common.tool_body(visit_common.mcp_call("caldera_write", {
        "method": "POST",
        "path": "/api/v2/operations",
        "body": payload,
    }))
    if err:
        return None, err
    data = body.get("data")
    if not isinstance(data, dict):
        data = body
    operation_id = data.get("id")
    links = []
    if operation_id:
        raw, link_err = get_path(
            f"/api/v2/operations/{operation_id}/links",
            ["id", "status", "paw", "host", "finish", "ability"],
        )
        if not link_err:
            links = as_rows(raw)
    return {
        "id": operation_id or "",
        "name": data.get("name") or payload["name"],
        "state": data.get("state") or "running",
        "group": group,
        "adversary": profile["name"],
        "started": data.get("start"),
        "links": links,
    }, None


def keys_for(agents):
    found = []
    for agent in agents:
        key = device_key(agent.get("host") or agent.get("device"))
        if key and key not in found:
            found.append(key)
    return found


def write_boards(ws, now, agents, abilities, profiles, facts, report, operations_written, groups):
    at = checked_at(now)
    agent_keys = keys_for(agents)
    save(ws, "campaigns/agents/enrolled.json", {
        "keys": agent_keys,
        "schema": "campaign-agents/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "agents": agents,
    }, "agents.schema.json")
    save(ws, "campaigns/abilities/relevant.json", {
        "keys": [],
        "schema": "campaign-abilities/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "abilities": abilities,
    }, "abilities.schema.json")
    save(ws, "campaigns/adversaries/relevant.json", {
        "keys": [],
        "schema": "campaign-adversaries/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "adversaries": [
            {
                "adversary_id": profile["adversary_id"],
                "name": profile["name"],
                "ability_ids": profile["ability_ids"],
            }
            for profile in profiles
        ],
    }, "adversaries.schema.json")
    save(ws, "campaigns/facts/lab.json", {
        "keys": [],
        "schema": "campaign-facts/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "facts": facts,
    }, "facts.schema.json")
    current = None
    if report["operations"]:
        last = report["operations"][-1]
        current = {
            "id": last.get("id") or last["name"],
            "name": last["name"],
            "state": last["state"],
            "group": last["group"],
            "adversary": last["adversary"],
        }
    save(ws, "campaigns/metadata.json", {
        "keys": agent_keys,
        "schema": "campaign-metadata/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "last_visit_id": operations_written[-1] if operations_written else None,
        "last_collected_at": at,
        "coverage": {"caldera": "complete" if agents else "partial"},
        "counts": {
            "agents": len(agents),
            "abilities": len(abilities),
            "adversaries": len(profiles),
            "facts": len(facts),
        },
        "current_operation": current,
        "next_test": {
            "group": groups[0],
            "adversary": profiles[0]["name"],
            "why": "Repeat this class on the next chaos visit.",
        } if groups and profiles else None,
    }, "metadata.schema.json")
    save(ws, "state/chaos.json", report, "chaos-state.schema.json")


def report_for(at, agents, groups, operations, headline, status):
    rows = []
    for operation in operations:
        links = operation.get("links") or []
        complete = sum(1 for link in links if isinstance(link, dict) and link.get("status") == 0)
        state = operation.get("state") or "running"
        if state not in {"running", "finished", "paused"}:
            state = "running"
        rows.append({
            "name": operation["name"],
            "group": operation["group"],
            "adversary": operation["adversary"],
            "state": state,
            "links_complete": complete,
            "links_read": len(links),
        })
    return {
        "keys": keys_for(agents),
        "schema": "chaos-state/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "status": status,
        "headline": headline,
        "next_action": "Correlate this window on the next telemetry visit." if rows else "Initiate chaos.",
        "groups": groups,
        "operations": rows,
    }


def stamp_operation(ws, now, operation, abilities):
    at = checked_at(now)
    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    folder = Path(ws) / "campaigns" / "operations"
    folder.mkdir(parents=True, exist_ok=True)
    while (folder / f"{stamp}.json").exists():
        now = now + timedelta(seconds=1)
        stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    links = [row for row in (link_row(link, abilities) for link in operation.get("links") or []) if row]
    state = operation.get("state") or "running"
    if state not in {"running", "finished", "paused", "blocked"}:
        state = "running"
    payload = {
        "keys": keys_for([{"host": link.get("host")} for link in links]),
        "schema": "campaign-operation/v1",
        "updated_at": at,
        "source_agent": "caldera-mcp",
        "status": state,
        "headline": f"{operation['adversary']} on {operation['group']} is {state}.",
        "next_action": "Read the links again when the operation finishes.",
        "operation": {
            "id": operation.get("id") or operation["name"],
            "name": operation["name"],
            "state": state,
            "group": operation["group"],
            "adversary": operation["adversary"],
            "started": operation.get("started"),
        },
        "links": links,
    }
    save(ws, f"campaigns/operations/{stamp}.json", payload, "operation.schema.json")
    stamps = sorted(folder.glob("*.json"))
    for path in stamps[:-10]:
        path.unlink()
    return stamp


def cmd(args):
    ws = resolve_workspace(args.workspace)
    if ws is None:
        return 1
    now = datetime.now(timezone.utc)
    bundle, err = load_caldera()
    if err:
        print(f'{{"error": "{err}"}}', file=sys.stderr)
        return 1
    agents, groups = enrolled(bundle["agents"], now)
    nets = chart_networks(ws)
    profiles = lab_profiles(bundle)
    environment = []
    matched_sources = []
    for profile in profiles:
        source = pair_source(profile, bundle["sources"])
        if source is None or not source_matches(source, nets):
            continue
        if not profile_safe(profile, bundle["abilities"]):
            continue
        environment.append(profile)
        if source not in matched_sources:
            matched_sources.append(source)
    facts = source_facts(matched_sources)
    abilities = kept_abilities(bundle, environment)
    selected = [profile for profile in environment if profile["kind"] in GOAL_KIND[args.goal]]
    started = []
    skipped = [
        profile["name"] for profile in profiles
        if profile["kind"] in GOAL_KIND[args.goal] and profile not in environment
    ]
    if args.command == "run" and nets and groups:
        planner_id = atomic_planner(bundle["planners"])
        if planner_id is None:
            print('{"error": "atomic planner is missing"}', file=sys.stderr)
            return 1
        active = running_pairs(bundle["operations"])
        for profile in selected:
            source = pair_source(profile, bundle["sources"])
            for group in groups:
                if (group, profile["name"]) in active:
                    started.append({
                        "id": "",
                        "name": f"{group}-{profile['kind']}",
                        "state": "running",
                        "group": group,
                        "adversary": profile["name"],
                        "started": None,
                        "links": [],
                    })
                    continue
                operation, op_err = create_operation(group, profile, source, planner_id, now)
                if op_err:
                    skipped.append(profile["name"])
                    continue
                started.append(operation)
    at = checked_at(now)
    if not nets:
        headline = "Network chart has no addresses. No operation started."
    elif args.command == "collect":
        headline = (
            f"{len(agents)} agents enrolled, {len(environment)} profiles match the network chart. "
            "No operation started."
        )
    elif not groups:
        headline = "No enrolled group. No operation started."
    elif not selected:
        headline = "No lab profile matches the network chart. No operation started."
    else:
        headline = f"Started {len(started)} operations on {', '.join(groups)}."
    status = "ok" if nets and not skipped and (args.command == "collect" or started or not selected) else "partial"
    if args.command == "run" and (not groups or not nets or not selected):
        status = "blocked"
    report = report_for(at, agents, groups, started, headline, status)
    written = []
    for operation in started:
        if operation.get("id"):
            written.append(stamp_operation(ws, now, operation, bundle["abilities"]))
            now = now + timedelta(seconds=1)
    try:
        write_boards(ws, now, agents, abilities, environment, facts, report, written, groups)
    except Exception as exc:
        print(f'{{"error": "workspace file invalid: {exc.__class__.__name__}"}}', file=sys.stderr)
        return 1
    print(visit_common.summary({
        "visit": "chaos",
        "command": args.command,
        "goal": args.goal,
        "status": status,
        "groups": groups,
        "agents": len(agents),
        "profiles": [profile["name"] for profile in selected or profiles],
        "operations": [row["name"] for row in report["operations"]],
        "skipped": skipped,
        "headline": headline,
        "wrote": "state/chaos.json",
    }))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--workspace", required=True)
    collect.set_defaults(goal="chaos")
    run = sub.add_parser("run")
    run.add_argument("--workspace", required=True)
    run.add_argument("--goal", choices=sorted(GOAL_KIND), default="chaos")
    args = parser.parse_args()
    try:
        return cmd(args)
    except Exception as exc:
        print(f'{{"error": "{exc.__class__.__name__}"}}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
