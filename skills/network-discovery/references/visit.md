# Network visit

One lab. One script. CML only.

## Run

`read_file` `inventory/network.json` first, when it exists. The lab
title is the one on the task line. If the task line names none, use
`lab_title` from that file. If neither exists, stop and say the lab
title is missing. Do not choose a lab from the list.

Then one `execute_command`, `execution_type: "mcp_orchestration"`.
Do not pass `timeout`. The script returns when the collect
finishes. Studio's own cap is the backstop for a hung container.
Use the path Studio shows for the attached
`network-discovery/scripts/visit_network.py`. Copy that absolute
path. The words `Internal directory` are a label, not a path.

Each `execute_command` is a new container. In that container the
workspace is the `file_explorer` folder beside `skills` on that same
absolute path. Copy that directory. Pass it as `--workspace`. Do
not pass the relative name `file_explorer`, and do not `cd`.

```text
python3 <copied script path> collect --workspace <copied file_explorer directory> --lab "<title>"
```

The last stdout line is the result. A line above it from the runtime
is not the result. Do not open the snapshot to fill the reply.

If stderr says `hai_mcp unavailable`, follow the manual order below.
Any other failure: one line from stderr, then stop. Do not collect
by hand.

## What the script keeps

From `cml_get_lab_details` with configurations requested:

- Every node the tool returns. `name` is `label`. `node_definition` is copied. `platform` is `iosxe` for `cat8000v`, `iosv`, `csr1000v`, and `iosvl2`; `nxos` for `nxosv` and `nxosv9000`; `asa` for `asav`; `ftd` for `ftdv`; `linux` for `ubuntu`, `alpine`, and `server`. Any other definition is copied unchanged. `group` is the value of a `group:` tag, else null. An IOS-XE check calls a device only when `platform` is `iosxe` and `access.restconf` is not null.
- Interface `label` on that node. `cidr` is `ip_address` when the interface object has one, else an `ip address` line parsed from `running_config`, else the same line from `bootstrap_config`, else null.
- Links whose interface ids resolve to a node label and an interface label.
- Every well-formed `pat:<external>:<internal>` tag, on `forwarded`. Internal `443` sets `access.restconf`. Internal `22` sets `access.ssh`. Both only when that internal port appears once on the node.

The configuration text is not written. A missing address stays null.
This visit does not call another platform to fill it.

## Manual order

Use this only when the script reports `hai_mcp unavailable`.

1. `cml_list_labs`. Keep the lab whose `title` equals the title you were given. Zero or more than one match: stop.
2. `cml_get_lab_details` for that id with `include_configurations=false`.
3. If no node has a `pat:` tag, one `cml_get_node_info` for those ids with `include_configuration=false`, and copy `tags` onto the nodes.
4. Build `inventory/network.json` from the nodes, links, and tags. Leave every `cidr` null. Do not request configurations in chat.
5. `write_file` the snapshot, then `network/metadata.json`. Write `network/<stamp>.json` only on a first visit or a real change. `read_file` the snapshot back.

## Reply

```text
Visit: network
Lab: <lab_title>
Coverage: <complete|partial|unavailable>
Devices: <n>
Links: <n>
Forwarded: <n>
Addresses: <n> of <n> interfaces
Stamp: <id or none>
Wrote: inventory/network.json
```
