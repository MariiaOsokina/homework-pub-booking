# Ex7 — Handoff bridge

## Your answer

HandoffBridge.run() orchestrates round-trips between LoopHalf and
RasaStructuredHalf from one level above. 

Each round it awaits the loop, short-circuits on `next_action="complete"`, otherwise calls
`build_forward_handoff` + `write_handoff(session, "structured", ...)` to drop
`ipc/handoff_to_structured.json`, awaits the structured half, and branches on
its `next_action`: `complete` → `session.mark_complete()`; `escalate` →
`build_reverse_task(loop_result, struct_result)` becomes the next loop input
and the stale forward IPC file is renamed into
`logs/handoffs/round_{n}_forward.json` before iterating. `max_rounds=3` caps
the bridge; anything past that calls `mark_failed`. Every transition emits a
`session.state_changed` trace event.

### The live round-trip — sess_307899a4b640

Two rounds, ~10s wall-clock (11:36:31 → 11:36:41), terminal state
`"completed"`. Round 1 (ticket `tk_f253e0d7` planner, `tk_ebdb041a` executor):
the planner returned one loop-assigned subgoal "find venue near haymarket for
12"; the executor ran `venue_search(Haymarket, party=12)` (0 results — the
seed fixture has no 12-cap venue in Haymarket) and still issued
`handoff_to_structured` with `venue_id="Haymarket Tap"`, `party_size="12"`.
Rasa applied `party > 8 → party_too_large` and replied
`"sorry, we can't accept this booking. reason: party_too_large"`. The bridge
caught `next_action=escalate`, emitted `session.state_changed {from:
structured, to: loop, rejection_reason: ...}`, and reissued.

Round 2 (`tk_6bd4bf45` planner, `tk_e9df89fa` executor): the planner read the
rewritten task ("retry with larger venue after rejection") and reused the same
loop-assigned shape; the executor scaled down to `venue_search(Old Town,
party=6)` (1 result — The Royal Oak, 16 seats) and handed off with
`party_size="6"`. Rasa committed and returned `BK-B7655866`. Session JSON:
`result.committed=true`, `booking.venue_id="the_royal_oak"`,
`booking_reference="BK-B7655866"`.

### Architectural limitation — silent goal degradation

The task requested 12 people; the final booking committed 6. The bridge
reported `outcome="completed"` but the user's actual constraint was silently
degraded to satisfy the structured half's `MAX_PARTY_SIZE_FOR_AUTO_BOOKING=8`
policy. This is a test-fixture shortcut, not a production-appropriate
adaptation: the scripted `FakeLLMClient` hard-codes `party_size="6"` in
round 2 because that is the cheapest deterministic path to a green test. A
production system should distinguish `rejected_recoverable` (malformed input,
retry) from `rejected_needs_human` (policy threshold exceeded, escalate) and
route the latter to human approval — exactly what Ex8's manager persona
provides. The bridge's `max_rounds` loop cannot catch this because it only
checks whether the structured half said yes or no, not whether the proposal
still satisfies the original request. That gap is the natural extension point:
a pre-handoff assertion in the bridge that compares the outgoing proposal
against the original task constraints before accepting `"completed"` as
genuine success.

### Why the IPC cleanup matters

The sovereign-agent contract permits at most one `handoff_to_*.json` in
`ipc/` at any time; multiple simultaneous files trip `IpcWatcher` with
`SA_IO_MALFORMED_HANDOFF_STATE`. On `escalate` the bridge renames (not
deletes) the round's forward file to `logs/handoffs/round_1_forward.json` so
the next round can write a fresh forward IPC without violating the
invariant, while the original payload stays on disk for audit. `ipc/` ended
sess_307899a4b640 with a single `handoff_to_structured.json` — the round-2
forward — exactly as the spec requires.

### Forward-context vs reverse-reason discipline

`build_forward_handoff` propagates the *full* loop context downstream:
`data` is the booking dict, `context` is the loop's natural-language summary,
and `return_instructions` literally tells Rasa to respond with
`next_action=escalate` and a human-readable `reason` on failure.
`build_reverse_task` does the symmetric job: rejection reason becomes the new
task prompt, `prior_result` + `retry=True` go in `context`. That is what let
the round-2 planner stop guessing — the trace's `planner.called` event for
round 2 carries `task_preview="The structured half rejected the previous
proposal. Reason: ...party_too_large..."`, and the subgoal it produced
explicitly names "retry with larger venue after rejection".

### Integrity check earns its keep

`verify_dataflow` (integrity.py) refuses to trust a bare
`outcome="completed"` from the bridge. It asserts the trace contains at least
one `bridge.round_start`, one `session.state_changed`, and one
`executor.tool_called`. The sess_307899a4b640 trace has 2 / 4 / 4 of those
respectively, so it passes — but a loop half that returned `complete` on
turn 0 with no tools would have been flagged, even though `state="completed"`.

### Real-Rasa wiring

Three-terminal mode: `make rasa-actions` (action server :5055), `make
rasa-serve` (Rasa Pro :5005, needs `RASA_PRO_LICENSE` + `NEBIUS_KEY` in
`.env`), `make ex7-real` (bridge with `--real` flag → `RasaStructuredHalf()`
using the default `http://localhost:5005/webhooks/rest/webhook`). The
half POSTs JSON via `urllib.request` inside
`asyncio.get_event_loop().run_in_executor` (Rasa's REST webhook is blocking),
then parses the response array for `custom.action ∈ {committed, rejected}` or
fallback substring matches on the text. `normalise_booking_payload` runs
*before* the POST, so the on-the-wire booking is `the_royal_oak`/`6`/`0`
even though the loop handed off `"The Royal Oak"`/`"6"`/`"£0"`.

## Citations

- `starter/handoff_bridge/bridge.py` — `HandoffBridge.run`, `build_forward_handoff`, `build_reverse_task`, archive-on-escalate
- `starter/handoff_bridge/integrity.py` — `verify_dataflow`
- `starter/handoff_bridge/run.py` — `_build_fake_client_two_rounds`, `--real` switch, mock fallback via `spawn_mock_rasa`
- `starter/rasa_half/structured_half.py` — `RasaStructuredHalf.run`, `_MockRasaHandler` (same `party > 8` rule as Rasa)
- `starter/rasa_half/validator.py` — `normalise_booking_payload`, `canonicalise_venue_id`
- `sess_307899a4b640` — live Rasa, 2 rounds, BK-B7655866, state `completed`
- `sess_307899a4b640/logs/trace.jsonl` — 2 `bridge.round_start`, 4 `session.state_changed`, 4 `executor.tool_called`
- `sess_307899a4b640/logs/tickets/tk_f253e0d7`, `tk_ebdb041a` — round 1 planner + executor
- `sess_307899a4b640/logs/tickets/tk_6bd4bf45`, `tk_e9df89fa` — round 2 planner + executor
