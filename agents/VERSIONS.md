# Prompt versions

Deployed model is **MiniMax** unless noted.

| Agent | Version | Model |
|-------|---------|-------|
| Chaos | 1.0.0 | MiniMax |
| Device Discovery | 1.0.0 | MiniMax |
| Network Discovery | 1.0.2 | MiniMax |

Device Discovery 1.0.0 (skill device-discovery 1.0.0, workspace-handoff 1.0.2): reads `inventory/network.json` and writes interface addresses, CDP neighbors, and one firewall file per device. IOS-XE and FTD only, and only when a forwarded port is set. The collect command does not pass `timeout`. MiniMax.

Chaos 1.0.0 (skill caldera-mcp 2.1.0, workspace-handoff 1.0.0): collect and run stay on `campaigns/`. The agent does not call CML or IOS-XE and does not write the network directory. MiniMax.

Network Discovery 1.0.2 (skill network-discovery 1.0.2, workspace-handoff 1.0.1): each device has `platform` from its CML node definition. An IOS-XE check calls only `platform` `iosxe` with `access.restconf` set. The collect command does not pass `timeout`. MiniMax.

Network Discovery 1.0.0 (skill network-discovery 1.0.0, workspace-handoff 1.0.0): one CML visit writes `inventory/network.json` for Caldera. The script keeps node configuration inside the sandbox and stores interface addresses it can parse. Forwarded ports come from `pat:` tags. IOS-XE is a later visit that reads `access.restconf.port`. MiniMax.
