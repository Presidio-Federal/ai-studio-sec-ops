# Campaign visit

One `execute_command`, `execution_type: "mcp_orchestration"`. Use the
path Studio shows for the attached `caldera-mcp/scripts/visit_chaos.py`.
Copy it. Do not retype a path from memory. The transcript may render
it as `Internal directory`; that is the real path.

Each `execute_command` is a new container. In that container the workspace is the `file_explorer` folder beside `skills` on the path Studio shows for `visit_chaos.py`. Copy that directory. Pass it as `--workspace`. Do not pass the relative name `file_explorer`, and do not `cd`.

```text
python3 <skill>/scripts/visit_chaos.py collect --workspace <file_explorer>
```

The last stdout line is the summary. Ignore any runtime line above it.
Reply from that line. Do not open the boards to fill it. Do not call
`caldera_get` unless stderr says `hai_mcp unavailable`. Do not call
a device.

## 1. What to keep

The script calls `caldera_status`, then the lists in `tools.md`.
You do not.

**Agents.** Keep a row when `trusted` is true and `last_seen` is
under two hours. `group` is the group the agent reported. `device`
is `host`. Write `campaigns/agents/enrolled.json`.

**Abilities.** Keep an ability only when a lab profile that matches
the network chart lists it. Store id, name, tactic, technique id,
and why it was kept. Write `campaigns/abilities/relevant.json`.
Discard every other ability. There are thousands. Do not page them
into the workspace. Do not start an ability on its own.

**Adversaries.** Keep a row whose name starts with `lab`, ignoring
case, or whose
`atomic_ordering` is entirely inside the relevant ability ids.
Write `campaigns/adversaries/relevant.json`.

**Facts.** Open a source only when its name starts with `lab`. Keep
a fact whose trait is `app.url` or `remote.host.ip` and whose
address is on the network chart. Write `campaigns/facts/lab.json`.

**Report.** Rewrite `state/chaos.json` after the boards. `headline`
is one sentence: how many agents and lab profiles are ready, and
that no operation was started. `operations` lists any operation this
visit found already running. `status` is `ok` when Caldera answered.

**Operations.** From the summary, keep a row whose name starts with
`lab-` or whose group matches an enrolled agent. A new id, or a
`state` that differs from `campaigns/metadata.json` `current_operation`,
is material: write `campaigns/operations/<stamp>.json` with link
rows (host, paw, ability name, technique id, status). Status `0`
is complete.

## 2. Learn

On `campaigns/metadata.json` set `next_test` only from this visit's
links. An ability that finished with status `0` is worth repeating.
A link that did not finish is not. `why` is one sentence. Leave
`next_test` null when nothing new was learned.

## 3. Run

Only on initiate chaos, start chaos, or run the lab. Follow
`references/run.md`. Do not ask the operator to name the adversary,
the source, or the group.

## Reply

Collect:

```text
Visit: campaign
Coverage: caldera <complete|partial|unavailable>
Agents: <n> enrolled
Abilities: <n> kept
Adversaries: <n> kept
Facts: <n>
Next test: <adversary or none>
Wrote: campaigns/metadata.json, state/chaos.json
```

Run:

```text
Operation: <name>
Group: <group>
Adversary: <name>
State: <state>
Wrote: campaigns/operations/<stamp>.json
Next test: <what the following visit should repeat or drop>
```
