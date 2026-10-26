# Device visit

The connector has the host. The script reads every selected device
and passes that device's forwarded port. You do not loop the tools
yourself unless the script cannot start. Do not ask for a host.

## Run

`read_file` `inventory/network.json` first. If it is missing, stop
and say the network directory is missing.

Then one `execute_command`, `execution_type: "mcp_orchestration"`.
Do not pass `timeout`. Do not pass a username or a password. The
script returns when the collect finishes. Studio's own cap is the
backstop for a hung container. Use the path Studio shows for the
attached `device-discovery/scripts/visit_device.py`. Copy it. Do
not retype a path from memory. The transcript may render it as
`Internal directory`; that is the real path. Do not pass those
words. Do not list the directory that contains `file_explorer`.

Each `execute_command` is a new container. In that container the
workspace is the `file_explorer` folder beside `skills` on that same
absolute path. Copy that directory. Pass it as `--workspace`. Do
not pass the relative name `file_explorer`, and do not `cd`.

```text
python3 <copied script path> collect --workspace <copied file_explorer directory>
```

Add `--device "<name>"` only when the task line names one device.
The name must match `devices[].name`. Do not add a second device to
the same command.

The last stdout line is the result. A line above it from the runtime
is not the result. Do not open the snapshot to fill the reply.

If stderr says `hai_mcp unavailable`, follow the manual order below.
Any other failure: one line from stderr, then stop. Do not collect
by hand.

## What the script keeps

From `inventory/network.json`: `lab_title`, `lab_id`, and each
selected device's `name`, `platform`, and `access.restconf.port`.
It does not rewrite that file.

IOS-XE: interface name, primary CIDR, and CDP neighbor rows. A name
that contains a dot is a subinterface. Its parent is the name before
the dot.

Firewall: logical `name`, `hardware` (the CML interface label when
they differ), CIDR, VLAN, zone, and `management_only`. Then zones,
network objects, and access rules in `network/firewall/<device>.json`.
An empty address on a parent interface stays null. Subinterface
addresses are separate rows.

A device that does not answer keeps its prior row and is
`unavailable`. One failed device does not stop the others. The
script stops on its own clock before starting another device and
returns. Do not pass `timeout`.

## Manual order

Use this only when the script reports `hai_mcp unavailable`. One
device. The first selected row. Then stop and name the next device.

1. Confirm `platform` is `iosxe` or `ftd` and `access.restconf.port` is set.
2. IOS-XE: the two reads in `tools.md`. Firewall: the paths in `tools.md`, then subinterfaces for each parent, then zones, objects, policies, and rules.
3. `write_file` the merged `network/endpoints/current.json` for that device only. Leave every other device row as it was.
4. For a firewall, `write_file` `network/firewall/<device>.json`.
5. `write_file` `network/endpoints/metadata.json`. Write `network/endpoints/<stamp>.json` only on a first visit or a real change. `read_file` the snapshot back.

## Reply

```text
Visit: devices
Lab: <lab_title>
Coverage: <complete|partial|unavailable>
Devices: <n> read, <n> failed, <n> remaining
Interfaces: <n> with addresses
Neighbors: <n>
Firewalls: <n>
Rules: <n>
Stamp: <id or none>
Wrote: network/endpoints/current.json
```
