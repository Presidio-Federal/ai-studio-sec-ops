---
name: network-discovery
version: "1.0.2"
description: "v1.0.2 — CML visit that writes inventory/network.json: devices, platform, links, forwarded ports, and interface addresses."
---

# Network discovery

One visit. You publish the network directory Caldera reads. You do
not start a Caldera operation. You do not call IOS-XE. You do not
change a lab, a node, a link, a tag, or a config.

The lab title comes from the task line, or from `lab_title` on
`inventory/network.json` when the task line names none. If both are
missing, stop and say the lab title is missing. Do not pick a lab
yourself.

A line that names the lab, or says to refresh the network, is
authorization. Do not ask again.

## Hard boundaries

Read tools only: `cml_list_labs`, `cml_get_lab_details`, and
`cml_get_node_info` when lab details returned no `pat:` tag. The
script requests configurations so it can parse interface addresses.
It does not write that text. A manual fallback, only when stderr
says `hai_mcp unavailable`, calls `cml_get_lab_details` with
`include_configurations=false` and leaves every `cidr` null.

Do not call a tool that creates, edits, starts, stops, or deletes
anything in CML. Do not guess a host, a port, or a lab title. An
external port is the number in a `pat:<external>:<internal>` tag.
Internal `443` is RESTCONF and internal `22` is SSH, and only when
that internal port appears once on the node. Other forwarded ports
stay on `forwarded[]`.

Do not write `campaigns/`, `health/`, `state/`, or a second
inventory file.

## Files

| Path | Kind | When |
|------|------|------|
| `inventory/network.json` | snapshot | Every successful collect. Replaced. |
| `network/metadata.json` | metadata | Every collect. |
| `network/<stamp>.json` | observation | First collect or a material change. Never overwrite. |

Paths: `references/workspace-contract.md`. Tools: `references/tools.md`.
Steps: `references/visit.md`.

## State machine

READ prior snapshot → LIST labs → DETAILS for the named title → WRITE snapshot and metadata → STAMP only when material → STOP.

A quiet collect rewrites the snapshot and metadata and does not add a stamp.

## Canonical top-level keys

Every structured JSON file you write requires top-level `keys`. Set it to the deduplicated union of every source-supported nested key and entity field in that file; use `[]` when there are none. Keep nested row `keys`. Keys must match exactly `^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`; never infer one. An interface key is `interface:<device>/<interface>`. A `pat:` tag is never a key.
