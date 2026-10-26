# Workspace — device map

This visit writes the interface map and the firewall files. It does
not write `inventory/network.json`, `network/metadata.json`, or
`campaigns/`. It does not write a RESTCONF body, an FDM object, or
a second inventory file.

Paths and readers: `workspace-handoff`. Schemas and examples live in
this skill.

| File | Kind | When |
|------|------|------|
| `network/endpoints/current.json` | snapshot | Every collect that selected a device. One lab. Other devices already in the file stay unless this visit read them or a full visit dropped them. |
| `network/endpoints/metadata.json` | metadata | That same collect. |
| `network/endpoints/<stamp>.json` | observation | First collect or a material change. Never overwrite. |
| `network/firewall/<device>.json` | snapshot | The firewall reached on this visit. The file name is the device `name`. A name that is not a single safe path segment is not written. |

A quiet success rewrites the endpoint snapshot and metadata and does
not add a stamp. `last_collected_at` moves. `last_visit_id` stays.

Material: an interface CIDR or zone changed, a CDP neighbor set
changed, a firewall zone, object, or rule changed, or a device row
appeared or disappeared. A new `collected_at` is not material. The
same device failing the same way on the next visit is not material.

A full visit drops an endpoint row whose device is no longer `iosxe`
or `ftd` with a forwarded port. A one-device visit replaces only
that device. A device that does not answer keeps the prior interface
rows and is marked `unavailable`.

`name` is the name the platform uses. On IOS-XE that is the interface
(`<interface>`). On a firewall it is the logical name (`<outside>`).
`hardware` is set when that label differs, and it is the label CML
already stored. The interface key uses `hardware` when it is set,
otherwise `name`. A subinterface is its own row. Its `parent` is the
hardware name of the parent. A firewall `neighbors` list is empty.

Keep 10 stamp files under `network/endpoints/`. Delete older stamps
after a write. Do not delete `current.json`, `metadata.json`, or
anything under `network/firewall/`.

Network Discovery's stamps are the JSON files directly in `network/`.
They are not these files.

## Canonical top-level keys

Every structured JSON file requires top-level `keys`. Set it to the
deduplicated union of every source-supported nested key. Use `[]`
when there are none. Keep nested row `keys`. A key matches
`^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`.
An interface key is `interface:<device>/<label>`. A device key is
`device:<name>` using the snapshot name. Do not invent one. A
neighbor host is not a key. A rule is not a key. A forwarded port
is not a key.
