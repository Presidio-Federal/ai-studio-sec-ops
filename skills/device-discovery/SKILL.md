---
name: device-discovery
version: "1.0.2"
description: "v1.0.2 — Device visit that writes interface addresses, CDP neighbors, and firewall rules from the network snapshot ports."
---

# Device discovery

One visit. You publish the interface map and the firewall files Caldera
can read. You do not start a Caldera operation. You do not call CML.
You do not change a device.

The connector already has the host. Do not ask for it. Pass each
device's forwarded port. Do not choose a host and do not read one
from the environment.

A device name on the task line limits the visit to that device. With
no device name, the visit reads every `iosxe` and `ftd` row in
`inventory/network.json` whose `access.restconf` is set. A device
with any other `platform`, or with no forwarded port, is skipped.

`inventory/network.json` must already exist. If it is missing, stop
and say the network directory is missing. Do not collect CML here.

A line that says to refresh the devices, or the map, is
authorization. Do not ask again.

## Hard boundaries

Read tools only: `iosxe_restconf_get` and `ftd_get`. Pass the
forwarded `port` from the snapshot. Omit `host`. Do not pass a
username or a password. Do not call an IOS-XE write tool. Do not call `ftd_post`,
`ftd_put`, `ftd_delete`, `ftd_deploy`, or `ftd_hit_counts`.

One device per tool call. The script does that. Do not put two ports
in one message.

Do not write `inventory/network.json`, `network/metadata.json`,
`campaigns/`, `health/`, or `state/`. Do not write a raw tool body.

## Files

| Path | Kind | When |
|------|------|------|
| `network/endpoints/current.json` | snapshot | Every collect that selected a device. Merged. One lab. |
| `network/endpoints/metadata.json` | metadata | That same collect. |
| `network/endpoints/<stamp>.json` | observation | First collect or a material change. Never overwrite. |
| `network/firewall/<device>.json` | snapshot | Each firewall the visit reached. Replaced for that device only. |

Paths: `references/workspace-contract.md`. Tools: `references/tools.md`.
Steps: `references/visit.md`.

## State machine

READ the snapshot and the prior map → SELECT `iosxe` and `ftd` rows with a forwarded port → FOR EACH device READ that platform and WRITE that device → STAMP only when material → STOP.

A quiet collect rewrites the snapshot and metadata and does not add a stamp. A failed device does not erase a prior row for that device.

## Canonical top-level keys

Every structured JSON file you write requires top-level `keys`. Set it to the deduplicated union of every source-supported nested key and entity field in that file; use `[]` when there are none. Keep nested row `keys`. Keys must match exactly `^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`; never infer one. An interface key uses the hardware name when the device has one, otherwise the interface name: `interface:<device>/<label>`. A device key is `device:<name>`. A neighbor name is not a key. A rule is not a key.
