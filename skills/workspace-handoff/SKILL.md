---
name: workspace-handoff
version: "1.0.2"
description: "v1.0.2 — Shared workspace contract: who writes each path, the envelope, keys, quiet visits, and how a visit script receives the workspace."
---

# Workspace handoff

The shared workspace is the state. This skill is the catalog: which
files exist, who writes each one, and which fields another agent may
read. The writer skill owns the schema, the example, and the procedure.
Load a schema only when you are that writer.

One writer per file. Source systems stay authoritative. The workspace
stores comparable facts and evidence references, not a copy of a tool
payload.

## Paths

| Tool | Path |
|------|------|
| Built-in file tools | a catalog row, as written below |
| `execute_command` | the `file_explorer` directory beside `skills` on the path Studio shows for the visit script. Copy that directory. Pass it as `--workspace`. |
| Skill files | skill-relative. Scripts resolve data from `Path(__file__)`. |

`read_file` and `write_file` take the catalog path (`inventory/network.json`).
They do not take `/workspace/`, `file_explorer`, or `Internal directory`.
Each `execute_command` is a new container. Do not `cd`. Do not pass the
relative name `file_explorer`. Do not retype a path from memory. A
transcript may render the real directory as `Internal directory`.

`write_file` creates parents. The agent never `mkdir`. Do not invent a
prefix or a second tree. Do not list `automations/schedules/`. That
folder is empty scratch, not the workspace.

Write only catalog paths. Do not write helper scripts, scratch dumps,
or raw tool payloads.

## Envelope

Coordination files (`state`, `request`, `result`) use:

```json
{
  "updated_at": "<timestamp>",
  "source_agent": "<writer>",
  "status": "ok",
  "headline": "<one line>",
  "next_action": "<what the next agent should do>"
}
```

Snapshots, observations, and metadata use the writer schema. A missing
required coordination input blocks only the action that depends on it.
A missing optional file is reduced coverage. Do not fill a gap from chat.

## Keys

Every structured JSON file has top-level `keys`. It is the deduplicated
union of the entities that file's source actually named. `[]` when the
source named none. Keep each row's `keys`. A key matches
`^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`.
An interface key is `interface:<device>/<interface>`. Do not invent an
id the payload did not contain.

## Quiet visits

Diff against the last published file, not against chat. A completed
collection with no material change updates metadata only: advance
`last_collected_at`, leave `last_visit_id` alone, and do not add a
stamp. A stamp is written on the first visit, when something material
changed, or when coverage is not complete. Stamps are
`YYYY-MM-DDTHH-MM-SSZ.json`, append-only. Open the prior stamp from
`last_visit_id`. Do not list the directory. The writer keeps 10 and
deletes older after the write.

## Catalog

| File | Kind | Writer | Schema | Readers may rely on |
|------|------|--------|--------|---------------------|
| `inventory/network.json` | snapshot | Network Discovery | `network-discovery` `schemas/network-inventory.schema.json` | `lab_title` `lab_id` `collected_at` `status` `devices[].name` `group` `node_definition` `platform` (`iosxe` `nxos` `asa` `ftd` `linux`, or the source definition) `access.restconf.port` `access.ssh.port` `forwarded[]` `interfaces[].name` `interfaces[].cidr` `links[]` `services[]` `keys`. Device Discovery reads rows whose `platform` is `iosxe` or `ftd` and whose `access.restconf` is not null. Caldera reads this file and does not write it. |
| `network/metadata.json` | metadata | Network Discovery | `network-discovery` `schemas/network-metadata.schema.json` | `last_visit_id` `last_collected_at` `visits[]` |
| `network/<stamp>.json` | observation | Network Discovery | `network-discovery` `schemas/network-visit.schema.json` | `visit_id` `checked_at` `coverage` `vs_prior.changed[]` `keys`. Written only when material. Files directly in `network/`, not `network/endpoints/` or `network/firewall/`. |
| `network/endpoints/current.json` | snapshot | Device Discovery | `device-discovery` `schemas/network-endpoints.schema.json` | `lab_title` `lab_id` `collected_at` `status` `devices[].name` `platform` `status` `interfaces[].name` `hardware` `cidr` `kind` `parent` `vlan` `zone` `management_only` `neighbors[].local_interface` `device` `port` `address` `platform` `keys`. Interface key uses `hardware` when set. Firewall neighbors are empty. |
| `network/endpoints/metadata.json` | metadata | Device Discovery | `device-discovery` `schemas/network-endpoints-metadata.schema.json` | `last_visit_id` `last_collected_at` `visits[]` |
| `network/endpoints/<stamp>.json` | observation | Device Discovery | `device-discovery` `schemas/network-endpoints-visit.schema.json` | `visit_id` `checked_at` `coverage` `vs_prior.changed[]` `keys`. Written only when material. |
| `network/firewall/<device>.json` | snapshot | Device Discovery | `device-discovery` `schemas/network-firewall.schema.json` | `device` `collected_at` `status` `policies[].name` `default_action` `zones[].name` `interfaces` `objects[].name` `kind` `value` `rules[].name` `action` `policy` `source_zones` `destination_zones` `source_networks` `destination_networks` `source_ports` `destination_ports` `keys`. One file per firewall. The file name is the device `name`. |
| `campaigns/metadata.json` | metadata | Caldera | `caldera-mcp` | `last_visit_id` `last_collected_at` `current_operation` `next_test` |
| `campaigns/agents/enrolled.json` | snapshot | Caldera | `caldera-mcp` | enrolled agents |
| `campaigns/abilities/relevant.json` | snapshot | Caldera | `caldera-mcp` | kept abilities |
| `campaigns/adversaries/relevant.json` | snapshot | Caldera | `caldera-mcp` | kept adversaries |
| `campaigns/facts/lab.json` | snapshot | Caldera | `caldera-mcp` | `trait` `value` |
| `campaigns/operations/<stamp>.json` | result | Caldera | `caldera-mcp` | one operation |

Network Discovery does not write `campaigns/`, `network/endpoints/`,
or `network/firewall/`. Device Discovery does not write
`inventory/network.json`, `network/metadata.json`, or `campaigns/`.
Caldera does not write `inventory/` or `network/`.
