# Prompt versions

Deployed model is **MiniMax** unless noted.

| Agent | Version | Model |
|-------|---------|-------|
| Network Discovery | 1.0.0 | MiniMax |

Network Discovery 1.0.0 (skill network-discovery 1.0.0, workspace-handoff 1.0.0): one CML visit writes `inventory/network.json` for Caldera. The script keeps node configuration inside the sandbox and stores interface addresses it can parse. Forwarded ports come from `pat:` tags. IOS-XE is a later visit that reads `access.restconf.port`. MiniMax.

Caldera skill 2.1.0: collect writes `campaigns/` from Caldera only. It reads `inventory/network.json` on a run and does not write it. No agent prompt yet. MiniMax.
