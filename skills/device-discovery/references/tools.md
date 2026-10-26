# Device tools

Read tools only. Names are from `docs/mcp-index.md`. Connection
credentials stay on the connector. The connector supplies the host.
Pass `port` only. Do not pass `host`, `username`, or `password`.
Do not ask for a host.

`port` is `access.restconf.port` on the device row. Do not guess it.

## IOS-XE

`iosxe_restconf_get(path, port, params)` returns
`{ok, status_code, method, path, data}`. `params.fields` limits the
body. Call a device only when `platform` is `iosxe`.

Interfaces:

```text
path: Cisco-IOS-XE-native:native/interface
fields: GigabitEthernet(name;ip/address/primary);TenGigabitEthernet(name;ip/address/primary);Ethernet(name;ip/address/primary);Loopback(name;ip/address/primary);Vlan(name;ip/address/primary);Port-channel(name;ip/address/primary)
```

If that call fails, one retry with
`GigabitEthernet(name;ip/address/primary);Loopback(name;ip/address/primary);Vlan(name;ip/address/primary)`.

Keep the interface name as the list name plus the `name` field
(`GigabitEthernet` and `1` become `GigabitEthernet1`). Keep a primary
address and mask as a CIDR. A missing primary stays null.

CDP:

```text
path: Cisco-IOS-XE-cdp-oper:cdp-neighbor-details
fields: cdp-neighbor-detail(device-name;local-intf-name;port-id;ip-address;platform-name)
```

Keep `local_interface`, `device`, `port`, `address`, and `platform`.
An empty body is zero neighbors, not a failed device. Do not copy
any other CDP field.

## Firewall

`ftd_get(path, port, params)` returns
`{ok, status_code, method, path, data}`. `path` is relative to
`/api/fdm/latest/`. `params` may be `limit` and `offset`. Call a
device only when `platform` is `ftd`. Page while `paging.count` is
greater than the items already kept.

| Path | Keep |
|------|------|
| `devices/default/interfaces` | `name`, `hardwareName`, `ipv4.ipAddress`, `mode`, `linkState`, `managementOnly` |
| `devices/default/interfaces/{id}/subinterfaces` | same fields, plus `vlanId`. `{id}` is the parent `id` from the interface list. A not-found on a parent means that parent has no subinterfaces. |
| `object/securityzones` | zone `name`, each interface `hardwareName` |
| `object/networks` | `name`, `subType`, `value`, `isSystemDefined` |
| `policy/accesspolicies` | policy `name`, `defaultAction.action` |
| `policy/accesspolicies/{id}/accessrules` | rule `name`, `ruleAction`, zone names, network names, port names |

The parent interface often has no address. The inside addresses are
on the subinterfaces. Join a zone to an interface by `hardwareName`.
Do not copy `version`, `links`, or the object id into the workspace.
The id is only the next path segment.

A firewall has no CDP neighbors. Leave `neighbors` empty. Do not
invent a neighbor from a CML link.
