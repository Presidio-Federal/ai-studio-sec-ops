# Tools this visit calls

CML read tools only. Names from the CML MCP server. Do not call
IOS-XE, Caldera, or any CML tool that creates, edits, starts, stops,
or deletes a lab, node, link, tag, or config.

| Tool | Use |
|------|-----|
| `cml_list_labs` | Resolve the lab title to one lab id. Exact title match. |
| `cml_get_lab_details` | Nodes, interface labels, links, tags. `include_configurations=true` only inside the visit script, so the script can read interface addresses and then discard the configuration text. |
| `cml_get_node_info` | Only when lab details returned no `pat:` tag on any node. `include_configuration=false`. |

`cml_list_labs` returns `{ok, labs:[{id, title, state}], total_labs}`.

`cml_get_lab_details` takes `lab_id` (id or title) and
`include_configurations`. It returns `{ok, lab_id, lab_title, nodes, links}`.
A node has `id`, `label`, `node_definition`, `state`, `tags`,
`interfaces`. An interface has `id`, `label`, and may have
`ip_address`. A link has `interface_a`, `interface_b`, `node_a`,
`node_b`, `label_a`, `label_b`. With configurations requested, a node
may also have `bootstrap_config` and `running_config`. Those strings
are input to the address parse. They are not a workspace field.

`cml_get_node_info` takes `lab_id`, `node_ids` (a JSON array of ids),
`include_configuration`, `include_interfaces`, `include_peers`.

A forwarded port is a node tag `pat:<external>:<internal>`, both
ports integers. Internal `443` is RESTCONF. Internal `22` is SSH.
Any other internal port stays on `forwarded[]` and does not set
`access`. The external port is whatever the tag says. Do not assume
a port, a host, or a range. The IOS-XE connector supplies its own
host. This file stores the external port only.
