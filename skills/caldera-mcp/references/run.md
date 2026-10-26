# Run

The agent runs `scripts/visit_chaos.py run` once, with
`execution_type: "mcp_orchestration"`. The script chooses the
profiles, the sources, and the groups. Do not ask the operator to
name them. Do not stop to confirm. Do not call `caldera_get`.

A narrower line still runs without a playbook name. Marks, DSCP,
ToS, or differentiated packets run the traffic profile only. Scan,
trigger, or detection runs the scan profile only. Application, dev,
or prod runs the application profile only. Initiate chaos, start
chaos, run the lab, or any other goal runs all three, traffic then
scan then application.

## 1. Groups

The script calls `caldera_status`, then reads agents. `include` is
a list inside the script.

An agent is eligible when `trusted` is true, `last_seen` is within
two hours, and `group` is not empty. Run one operation for each
distinct group among those agents. Do not read
`inventory/network.json` to pick the group. Do not invent a group.
An empty `group` hits every agent. Skip an agent whose group is
empty and name that host in the reply. Do not deploy an agent.

## 2. Profiles

List adversaries. Keep a row whose name starts with `lab`, ignoring
case. Read its description and the names of the abilities in
`atomic_ordering`. Drop `command`. Every kept ability must be
tactic `discovery` and must open a connection.

Classify each adversary:

- marked packets, DSCP, ToS, or SYN → traffic
- a port scan → scan
- an application or HTTP request → application

A class with no adversary is named in the reply. The other classes
still run.

Planner: the one whose `name` is `atomic`.

## 3. Source

List sources. Keep `trait` and `value`. Do not replace facts.

Pair an adversary with the source whose name shares a word with it:
traffic, scan, or app. When two sources carry the same trait, that
shared word is the pair. Traffic and scan need `remote.host.ip`.
Application needs `app.url`. If no source pairs, skip that adversary
and say so.

## 4. Already running

`caldera_get` `/api/v2/operations/summary`. If that adversary and
that group are `state` `running`, do not create another. Say it is
already running and continue with the next pair.

## 5. Create

One `caldera_write` `POST /api/v2/operations` per pair, in class
order, and within a class one group at a time. The body is in
`tools.md`. `name` is `<group>-<kind>-<YYYYMMDDTHHMMZ>`. `kind` is `traffic`,
`scan`, or `application`.

After each create, one read of `/api/v2/operations/{id}/links`.
Keep `id`, `status`, `paw`, `host`, `decide`, `finish`, and ability
`name`, `tactic`, `technique_id`. Drop every command field. Status
`0` is complete. Any other number is not. Do not poll.

## 6. Write

One `campaigns/operations/<stamp>.json` per operation you created
or found already running. Stamp `YYYY-MM-DDTHH-MM-SSZ`. Then
rewrite `campaigns/metadata.json` and replace `state/chaos.json`.
`headline` is one sentence of what started, on which groups.
`operations` is one row per operation: name, group, adversary,
state, and link counts. No command text. `next_test` on the
metadata is the class you would repeat. `next_action` on the
report is that same sentence. Keep 10 stamps. Delete older after
the write. Do not delete `state/chaos.json`.

## Reply

One block per operation:

```text
Operation: <name>
Group: <group>
Adversary: <name>
State: <running|finished|paused>
Agents: <n eligible>
Links: <n complete> / <n read>
Wrote: campaigns/operations/<stamp>.json, state/chaos.json
```

End with `Next: <what a later visit should repeat>`.

Pause or finish only when the operator says pause or finish and
names the operation. `PATCH` `state` only.
