# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 run (sess_307899a4b640), the planner never assigned a subgoal directly to the structured half. The round-1 planner ticket tk_f253e0d7/raw_output.json produced exactly one subgoal:
json{
  "id": "sg_1",
  "description": "find venue near haymarket for 12",
  "success_criterion": "candidate identified",
  "assigned_half": "loop",
  "status": "pending"
}
The ticket's summary.md confirms: "Planner produced 1 subgoals. 1 to loop half, 0 to structured half." Round 2 (tk_6bd4bf45) follows the same pattern — assigned_half: "loop" for subgoal "retry with larger venue after rejection."
The actual transition to the structured half happened one layer below the planner, inside that loop subgoal. Executor ticket tk_ebdb041a/raw_output.json shows two tool calls: first venue_search(Haymarket, party=12) returning 0 results, then handoff_to_structured with reason:

"loop half identified a candidate venue; passing to structured half for confirmation under policy rules"

The executor's manifest flags handoff_requested: true — that is what the bridge actually dispatched on, emitting session.state_changed {from: "loop", to: "structured"} in the trace.
The signal that triggered the handoff was the LLM matching task prose against two generic prompts inside sovereign-agent, not any booking-specific rule. The handoff_to_structured tool is registered with the description "Hand off control to the structured half for rule-following work" (sovereign_agent/tools/builtin/__init__.py:199), and the executor's system prompt adds: "If the subgoal needs a destructive or high-stakes action, call handoff_to_structured rather than performing the action yourself" (sovereign_agent/executor/__init__.py:63-65). Neither mentions bookings. The LLM had to bridge "book a venue for 12 people" → "high-stakes destructive action requiring rule-following confirmation" entirely on its own, then pick the tool whose description loosely matched. The planner picked "loop" for the same reason in reverse — nothing in "find venue near haymarket for 12" reads as a rule-check, so it stayed on the loop side.
So the handoff is a tool call inside a loop-assigned subgoal, not a planner decision. The planner says "go research a venue"; the executor researches, then decides on its own to invoke handoff_to_structured. The bridge only acts when it sees handoff_requested: true in the executor's output.
The practical consequence: if the LLM had finished the subgoal without calling handoff_to_structured, the bridge would have had nothing to dispatch and the session would have ended at the loop half with no booking — there is no hardcoded "after research, hand off" rule.

### Citation

sessions/examples/ex7-handoff-bridge/sess_307899a4b640/logs/tickets/tk_f253e0d7/raw_output.json (planner round 1, assigned_half: "loop")
sessions/examples/ex7-handoff-bridge/sess_307899a4b640/logs/tickets/tk_f253e0d7/summary.md (planner subgoal distribution)
sessions/examples/ex7-handoff-bridge/sess_307899a4b640/logs/tickets/tk_ebdb041a/raw_output.json (executor round 1, handoff_to_structured call with verbatim reason)
sessions/examples/ex7-handoff-bridge/sess_307899a4b640/logs/tickets/tk_ebdb041a/manifest.json (handoff_requested: true)
sessions/examples/ex7-handoff-bridge/sess_307899a4b640/SESSION.md (original task framing)
.venv/lib/python3.12/site-packages/sovereign_agent/tools/builtin/__init__.py line 199 (handoff tool description)
.venv/lib/python3.12/site-packages/sovereign_agent/executor/__init__.py lines 63-65 (executor system prompt)

---

## Q2 — Dataflow integrity catch

### Your answer

My final session sess_2ee7bbbedea2 ran cleanly — verify_dataflow returned
ok=True with all 4 extracted flyer facts (£556, £111, 12°C, "cloudy") traced
to tool outputs. So I'll describe a specific test case that demonstrates
what the check WOULD catch, which manual review would miss.

Test case construction:

Modify _build_fake_client in run.py to make the scripted executor pass a
fabricated total to generate_flyer. Replace the line that derives
total_gbp from calculate_cost's output:

    # Replace this:
    "total_gbp": calc_output["total_gbp"],
    # With this:
    "total_gbp": 580,  # close to real value of 556

Run `make ex5` and inspect workspace/flyer.html. A human reviewer sees
"Total: £580" for a 6-person, 3-hour booking with bar snacks — entirely
plausible. The deposit would still show £111 (real), so the numbers
appear internally consistent. Manual skim: PASS.

What verify_dataflow catches:

extract_money_facts in integrity.py finds £580 in the flyer HTML.
fact_appears_in_log scans _TOOL_CALL_LOG for "580" in any tool's output
dict. calculate_cost's actual output contains subtotal=324, service=32,
total=556, deposit=111 — never 580. The check returns ok=False with
unverified_facts=['£580'].

Why this matters:

The check compares against ground-truth tool outputs, not against
"does this look reasonable." A £580 fabrication is harder to spot than
£9999 because it falls within the plausible range for the scenario.
Manual review fails on plausibility; verify_dataflow succeeds because
it requires provenance.

To make the test even sharper: also fabricate temperature_c=14
(close to real value 12). extract_temperature_facts would catch this
identically, proving the check generalises beyond money.

### Citation

- starter/edinburgh_research/integrity.py:fact_appears_in_log
- starter/edinburgh_research/run.py:_build_fake_client
- sessions/examples/ex5-edinburgh-research/sess_2ee7bbbedea2/workspace/flyer.html
---

## Q3 — Removing one framework primitive

### Your answer

I'd keep session directories (Decision 1) as the last thing standing
and rebuild everything else if forced. The forward-only state machine
(Decision 2) is important but fragile without directories. Tickets
(Decision 3) I could rebuild as .jsonl files inside the session.
Atomic-rename IPC (Decision 5) is replaceable by directory polling.

Session directories are the irreplaceable piece. Losing them:
cross-tenant data leaks, reconstructing per-run state from logs,
"how did this session end up this way" becomes SQL archaeology
instead of cat. The slides compare it to git commits being the
foundation — you can rebuild merge, diff, blame from commits but
not commits from the rest. Session directories are commits.

### Citation

- sessions/sess_de44a1b8eb12/ — the directory itself
- sessions/sess_a382a2149fc1/logs/trace.jsonl
