# Workspace — network directory

This visit writes the directory Caldera reads. It does not write
`campaigns/`, `health/`, or `state/`. It does not write a node
configuration, a topology export, or a second inventory file.

Paths and readers: `workspace-handoff`. Schemas and examples live in
this skill.

| File | Kind | When |
|------|------|------|
| `inventory/network.json` | snapshot | Every successful collect. Replaced. One lab. |
| `network/metadata.json` | metadata | Every collect, including a failed one that leaves the snapshot untouched. |
| `network/<stamp>.json` | observation | First successful collect, a material change, or coverage that is not `complete`. Never overwrite. |

A quiet success rewrites the snapshot and metadata and does not add
a stamp. `last_collected_at` moves. `last_visit_id` stays.

Material: a device appeared or disappeared, a `forwarded` pair
changed, an interface `cidr` changed, or a link appeared or
disappeared. A new `collected_at` is not material.

The snapshot's `lab_title` is the title passed into the visit. A
different title replaces the file; it does not merge two labs.

Keep 10 files under `network/` besides `metadata.json`. Delete older
stamps after a write. Do not delete `network/metadata.json` or
`inventory/network.json`.

## Canonical top-level keys

Every structured JSON file requires top-level `keys`. Set it to the
deduplicated union of every source-supported nested key. Use `[]`
when there are none. Keep nested row `keys`. A key matches
`^(device|interface|site|service|test|control|incident|change|application):[^ ].*$`.
An interface key is `interface:<device>/<interface>`. A device key is
`device:<name>` using the node label the tool returned. Do not invent
one. A `pat:` tag is not a key.
