"""Ex6 — runner (reference solution).

Modes:
  python -m starter.rasa_half.run                  # tier 1 mock, no services
  python -m starter.rasa_half.run --real           # tier 2 assume Rasa is up
  python -m starter.rasa_half.run --real --auto    # tier 3 auto-spawn Rasa

Booking cases (for rubric coverage — Ex6 awards 3 pts each for the two
rejection rules):
  --case happy            (default) party=6,  deposit=£200 → expect confirm
  --case reject-party     party=10, deposit=£200          → expect rejection (party_too_large)
  --case reject-deposit   party=6,  deposit=£400          → expect rejection (deposit_too_high)
"""

from __future__ import annotations

import asyncio
import json
import sys

from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.session.directory import create_session
from sovereign_agent.session.state import now_utc

from starter.rasa_half.structured_half import (
    RasaHostLifecycle,
    RasaStructuredHalf,
    spawn_mock_rasa,
)

_BOOKING_CASES: dict[str, dict] = {
    "happy": {
        "action": "confirm_booking",
        "venue_id": "Haymarket Tap",
        "date": "25th April 2026",
        "time": "7:30pm",
        "party_size": "6",
        "deposit": "£200",
    },
    "reject-party": {
        "action": "confirm_booking",
        "venue_id": "Haymarket Tap",
        "date": "25th April 2026",
        "time": "7:30pm",
        "party_size": "10",  # > 8 → party_too_large
        "deposit": "£200",
    },
    "reject-deposit": {
        "action": "confirm_booking",
        "venue_id": "Haymarket Tap",
        "date": "25th April 2026",
        "time": "7:30pm",
        "party_size": "6",
        "deposit": "£400",  # > £300 → deposit_too_high
    },
}


def _pick_case(argv: list[str]) -> str:
    for i, arg in enumerate(argv):
        if arg == "--case" and i + 1 < len(argv):
            return argv[i + 1]
    return "happy"


def _safe_update_state(session, *, target_state: str, structured: dict) -> None:
    """Transition through the forward-only sovereign_agent state machine.

    Background: sovereign_agent enforces ALLOWED_TRANSITIONS — you cannot
    jump directly from 'planning' to a terminal state. The legal path
    that Ex5 uses is planning → executing → <terminal>. We replicate
    that here, swallowing each transition's exception so the run still
    completes even if state names differ slightly across versions.

    To inspect the exact allowed states in your install, run:
        python -c "import sovereign_agent.session.state as s; \\
                   import inspect; print(inspect.getsource(s))"
    """
    # Step 1: planning → executing.
    try:
        session.update_state(state="executing", structured=structured)
    except Exception:
        pass  # already past planning, or 'executing' alias differs

    # Step 2: executing → terminal. Try canonical, then known aliases.
    if target_state == "completed":
        candidates = ["completed", "complete", "done", "success"]
    else:
        candidates = ["failed", "escalated", "escalate", "errored", "complete"]

    last_err: Exception | None = None
    for s in candidates:
        try:
            session.update_state(state=s, structured=structured)
            print(f"   ✓ session state → {s!r}")
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue

    print(
        f"   ⚠ could not reach terminal state from 'executing' (last error: {last_err}); "
        "trace event + result log still written"
    )


async def run_scenario(real: bool, auto: bool, case: str) -> int:
    if case not in _BOOKING_CASES:
        print(
            f"✗ unknown --case '{case}'. Pick one of: {', '.join(_BOOKING_CASES)}",
            file=sys.stderr,
        )
        return 2

    with example_sessions_dir("ex6-rasa-half", persist=real) as sessions_root:
        session = create_session(
            scenario="ex6-rasa",
            task=f"Confirm a booking through the Rasa structured half (case={case}).",
            sessions_dir=sessions_root,
        )
        print(f"📂 Session {session.session_id}")
        print(f"   dir:  {session.directory}")
        print(f"   case: {case}")

        sample_booking = {"data": dict(_BOOKING_CASES[case])}

        if real and auto:
            log_dir = session.logs_dir / "rasa"
            log_dir.mkdir(parents=True, exist_ok=True)
            print(f"   Rasa logs: {log_dir}")
            print(
                "   (tier 3 auto-spawn mode — the scenario spawns Rasa + action\n"
                "    server subprocesses, runs, then tears them down)"
            )
            async with RasaHostLifecycle(log_dir=log_dir) as rasa_url:
                print(f"   Rasa URL: {rasa_url}")
                half = RasaStructuredHalf(rasa_url=rasa_url, request_timeout_s=30.0)
                result = await half.run(session, sample_booking)

        elif real:
            print(
                "   (tier 2: assuming rasa-actions + rasa-serve are already\n"
                "    running in two other terminals. If you see a connection\n"
                "    error below, run `make ex6-help` for the setup recipe.)"
            )
            rasa_url = "http://localhost:5005/webhooks/rest/webhook"
            print(f"   Rasa URL: {rasa_url}")
            half = RasaStructuredHalf(rasa_url=rasa_url, request_timeout_s=30.0)
            result = await half.run(session, sample_booking)

        else:
            print("   (tier 1: stdlib mock Rasa on :5905 — no license needed)")
            server, _thread, mock_url = spawn_mock_rasa(port=5905)
            try:
                print(f"   Mock URL: {mock_url}")
                half = RasaStructuredHalf(rasa_url=mock_url)
                result = await half.run(session, sample_booking)
            finally:
                server.shutdown()

        print(f"\nStructured half outcome: {result.next_action}")
        print(f"  summary: {result.summary}")
        print(f"  output:  {result.output}")

        # Trace event — citable artifact for Ex9.
        session.append_trace_event(
            {
                "event_type": "structured_half.completed",
                "actor": "rasa",
                "timestamp": now_utc().isoformat(),
                "payload": {
                    "case": case,
                    "success": result.success,
                    "next_action": result.next_action,
                    "booking_reference": result.output.get("booking_reference"),
                    "summary": result.summary,
                },
            }
        )

        _safe_update_state(
            session,
            target_state="completed" if result.success else "failed",
            structured={"last_result": result.output, "case": case},
        )

        # Result log alongside the trace.
        try:
            log_path = session.logs_dir / "structured_half_result.json"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                json.dumps(
                    {
                        "case": case,
                        "success": result.success,
                        "next_action": result.next_action,
                        "summary": result.summary,
                        "output": result.output,
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            print(f"   ✓ structured result saved to: {log_path}")
        except OSError as e:
            print(f"   ⚠ could not write result log: {e}")

        if real:
            print(f"\n📂 Session artifacts: {session.directory}")
            print(f"📜 Narrate this run:   make narrate SESSION={session.session_id}")

        if case == "happy":
            return 0 if result.success else 1

        rejected_as_expected = (
            not result.success
            and isinstance(result.output, dict)
            and result.output.get("rejected") is True
        )
        if rejected_as_expected:
            print(f"   ✓ rejection observed as expected for case={case}")
            return 0
        print(f"   ✗ expected rejection for case={case}, got success={result.success}")
        return 1


def main() -> None:
    real = "--real" in sys.argv
    auto = "--auto" in sys.argv
    case = _pick_case(sys.argv)
    if auto and not real:
        print("✗ --auto requires --real", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(run_scenario(real=real, auto=auto, case=case)))


if __name__ == "__main__":
    main()
