---
name: caldera-mcp
version: "2.3.0"
description: "v2.3.0 — Caldera nurse: initiate chaos runs in one orchestration script and writes state/chaos.json."
---

# Caldera skill

One visit. You keep the campaign chart. When the line says initiate
chaos, you start the lab operations from abilities already on that
chart. You do not gather network data. You do not call CML or
IOS-XE. You do not change device config. You do not write `health/`
or `campaigns/network/`. The visit report is `state/chaos.json`.

A line that says to refresh the campaign, or names Caldera with no
run, is a collect. A line that says initiate chaos, start chaos, or
run the lab is authorization. Do not ask which adversary, which
source, or which group.

The chart is `campaigns/`. Subdirectories are `agents`, `abilities`,
`adversaries`, `facts`, and `operations`. Keep a row only when it
is a lab campaign. Drop the rest of the Caldera catalog. An ATT&CK
technique id is a field, not a key.

## Hard boundaries

Do not `POST` `/api/v2/abilities`. The server rejects ability
writes, payloads, deploy commands, and link command updates. A new
test is a new adversary whose `atomic_ordering` is ability ids
already in `campaigns/abilities/relevant.json`, plus facts already
in `campaigns/facts/lab.json`.

Do not copy `command`, `plaintext_command`, `output`, or `executor`
into the workspace or the reply.

Do not keep an ability whose tactic is exfiltration, lateral
movement, impact, credential access, or defense evasion. Do not
start Everything Bagel, Thief, Ransack, Worm, Lateral Movement, or
stockpile Discovery.

An empty `group` hits every agent. Do not send one. Do not start a
second operation while one with the same adversary and group is
`running`.

This visit does not push a firewall rule. `next_test` on the board
is the next campaign.

## Files

| Path | Kind | When |
|------|------|------|
| `campaigns/metadata.json` | metadata | Every visit. |
| `campaigns/agents/enrolled.json` | snapshot | Every collect. Replaced. |
| `campaigns/abilities/relevant.json` | snapshot | Every collect. Replaced. |
| `campaigns/adversaries/relevant.json` | snapshot | Every collect. Replaced. |
| `campaigns/facts/lab.json` | snapshot | Every collect. Replaced. |
| `campaigns/operations/<stamp>.json` | result | A run, or a collect that finds a new or changed lab operation. Never overwrite. |
| `state/chaos.json` | state | Every visit. Replaced. The concise report. |

Paths: `references/workspace-contract.md`. Tools: `references/tools.md`.
A collect follows `references/visit.md`. Initiate chaos follows
`references/run.md`.

The visit is one `execute_command` with
`execution_type: "mcp_orchestration"`. Do not pass `timeout`. The
script is `scripts/visit_chaos.py`. Copy its absolute path. Pass
the copied `file_explorer` directory as `--workspace`. Do not call
`caldera_get` yourself. `include` is a list inside the script.

```text
python3 <copied script path> collect --workspace <copied file_explorer directory>
python3 <copied script path> run --workspace <copied file_explorer directory> --goal chaos
```

`--goal` is `traffic`, `scan`, or `application` when the line names
one class. Otherwise `chaos`.

## State machine

Collect: RUN `visit_chaos.py collect` → it writes the five boards and `state/chaos.json` → STOP.

Run: RUN `visit_chaos.py run` → it chooses every lab profile and every enrolled group, creates those operations, and writes one `campaigns/operations/<stamp>.json` per operation, `state/chaos.json`, and metadata → STOP.

## Canonical top-level keys

Every structured JSON file you write requires top-level `keys`. Set it to the deduplicated union of every source-supported nested key and entity field in that file; use `[]` when there are none. Keep nested row `keys`. Keys must match exactly `^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`; never infer one. Use `site:` for location. An enrolled host name is `device:`. A technique id is never a key.
