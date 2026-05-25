# Ex6 — Rasa structured half

## Your answer

`RasaStructuredHalf.run()` takes a raw booking dict, normalises it through
`normalise_booking_payload` (validator.py), POSTs the result to Rasa's
REST webhook with a stable `sha1(venue|date|time)[:8]` sender_id, and
parses the response array for `{action: committed}` or `{action: rejected}`
custom slots — returning a `HalfResult` either way.

The validator covers all 5 rubric fields (date, currency, party_size,
time, venue_id), exceeding the "at least 3" threshold: dates accept
"25th April 2026" alongside ISO 8601, currency strips `£`/`GBP`,
venue_id lower-snake-cases (`"Haymarket Tap"` → `"haymarket_tap"`),
time parses both 12- and 24-hour input.

### Three rubric paths, three session traces

- **Confirm** — `sess_39131c77121d` (party=6, deposit=£200): Rasa
  returned `action=committed` with reference `BK-7D401E9E`. HalfResult:
  `success=true, next_action="complete"`. Session state: `completed`.
- **Reject party_size > 8** — `sess_a6e920d219da` (party=10): Rasa
  returned `"...party_too_large"`. HalfResult: `success=false,
  output.rejected=true, output.reason="...party_too_large"`. Session
  state: `failed`.
- **Reject deposit > £300** — `sess_3d3fa56f79c1` (deposit=£400):
  same shape with `deposit_too_high`. Session state: `failed`.

### Two design choices

**Network errors are distinguishable from policy rejections.** When
Rasa is unreachable (`sess_941021b35715`, `sess_f109813864be`), the
half returns `output.error_code: "SA_EXT_SERVICE_UNAVAILABLE"`. When
Rasa applies a rule, it returns `output.rejected: true` with a reason.
Both produce `next_action="escalate"`, but Ex7's bridge can tell
retry-worthy transients from policy-rejected bookings by inspecting
the output shape.

**Validation errors stay in-process.** `ValidationFailed` from the
normaliser is caught in `run()` and returned as a HalfResult — the
contract requires a result, not an exception.

### Changes I made to run.py

The starter `run.py` called the structured half directly without writing
anything back to the session, so `logs/` stayed empty and state stayed
at `"planning"` forever — nothing to cite for Ex9. I extended it to:

- emit a `structured_half.completed` trace event after each run
- write the full HalfResult to `logs/structured_half_result.json`
- advance the session state via `planning → executing → completed/failed`
  (sovereign_agent's machine is forward-only; direct jumps raise
  `SA_VAL_INVALID_STATE_TRANSITION`, so the runner bridges through
  `executing` first)
- add a `--case {happy, reject-party, reject-deposit}` flag so all three
  rubric paths run from a single entrypoint

## Citations

- `starter/rasa_half/validator.py` — normalise_booking_payload + helpers
- `starter/rasa_half/structured_half.py` — RasaStructuredHalf.run
- `starter/rasa_half/run.py` — trace events, result log, state transitions, `--case`
- `sess_39131c77121d` (happy) — confirmed, ref `BK-7D401E9E`, state `completed`
- `sess_a6e920d219da` (reject-party) — `party_too_large`, state `failed`
- `sess_3d3fa56f79c1` (reject-deposit) — `deposit_too_high`, state `failed`
- `sess_941021b35715`, `sess_f109813864be` — `SA_EXT_SERVICE_UNAVAILABLE`