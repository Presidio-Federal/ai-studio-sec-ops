# Prompt versions

Deployed model is **MiniMax** unless noted.

| Agent | Version | Model |
|-------|---------|-------|
| Chaos | 1.3.2 | MiniMax |
| Device Discovery | 1.0.2 | MiniMax |
| Network Discovery | 1.0.3 | MiniMax |

Chaos 1.3.2 (skill caldera-mcp 2.4.2, workspace-handoff 1.0.3): workspace handling matches health-logging. First read is `inventory/network.json`. The script accepts `--workspace` only when that file is in the directory. The command copies the path Studio shows for `caldera-mcp/scripts/visit_chaos.py`. MiniMax.

Chaos 1.3.1 (skill caldera-mcp 2.4.1, workspace-handoff 1.0.3): the visit copies the script path Studio shows for the attached skill. It does not list the workspace root, `/skills`, or `/shared_workspace`. Built-in file tools take catalog paths. MiniMax.

Network Discovery 1.0.3 (skill network-discovery 1.0.3) and Device Discovery 1.0.2 (skill device-discovery 1.0.2): same path rule. Copy the path Studio shows. Do not list the directory that contains `file_explorer`. MiniMax.

Chaos 1.3.0 (skill caldera-mcp 2.4.0, workspace-handoff 1.0.3): initiate chaos starts a lab profile only when every fact on its source is an address already on the network chart. Stock abilities are not operations. One operation per enrolled group. MiniMax.

Chaos 1.2.0 (skill caldera-mcp 2.3.0, workspace-handoff 1.0.3): the visit is one orchestration script. The model does not call `caldera_get`. `include` is a list inside the script. Initiate chaos still runs every lab profile on every enrolled group and rewrites `state/chaos.json`. MiniMax.

Device Discovery 1.0.1 (skill device-discovery 1.0.1, workspace-handoff 1.0.2): the connector supplies the host. The visit passes each device's forwarded port and does not ask for a host. MiniMax.

Device Discovery 1.0.0 (skill device-discovery 1.0.0, workspace-handoff 1.0.2): reads `inventory/network.json` and writes interface addresses, CDP neighbors, and one firewall file per device. IOS-XE and FTD only, and only when a forwarded port is set. The collect command does not pass `timeout`. MiniMax.

Chaos 1.1.1 (skill caldera-mcp 2.2.1, workspace-handoff 1.0.3): every visit rewrites `state/chaos.json`, a one-page report of the groups and operations. The operation stamps stay the detail. MiniMax.

Chaos 1.1.0 (skill caldera-mcp 2.2.0, workspace-handoff 1.0.2): initiate chaos runs every lab profile on every enrolled group. The agent chooses the adversary, the source, and the groups. It does not ask. MiniMax.

Chaos 1.0.0 (skill caldera-mcp 2.1.1, workspace-handoff 1.0.0): a run uses the adversary and source the operator names and does not replace that source. Collect keeps adversaries whose names start with `lab`. MiniMax.

Chaos 1.0.0 (skill caldera-mcp 2.1.0, workspace-handoff 1.0.0): collect and run stay on `campaigns/`. The agent does not call CML or IOS-XE and does not write the network directory. MiniMax.

Network Discovery 1.0.2 (skill network-discovery 1.0.2, workspace-handoff 1.0.1): each device has `platform` from its CML node definition. An IOS-XE check calls only `platform` `iosxe` with `access.restconf` set. The collect command does not pass `timeout`. MiniMax.

Network Discovery 1.0.0 (skill network-discovery 1.0.0, workspace-handoff 1.0.0): one CML visit writes `inventory/network.json` for Caldera. The script keeps node configuration inside the sandbox and stores interface addresses it can parse. Forwarded ports come from `pat:` tags. IOS-XE is a later visit that reads `access.restconf.port`. MiniMax.
