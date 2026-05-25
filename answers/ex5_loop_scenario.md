# Ex5 — Edinburgh research loop scenario

## Your answer

The planner produced 2 subgoals (ticket tk_4a282dee, planner.plan, 16.8s,
777/2960 tokens with Qwen3-Next-80B-A3B-Thinking): sg_1 for research
(venue_search, get_weather, calculate_cost) and sg_2 for flyer generation
(generate_flyer, complete_task). Both assigned to loop half, with sg_2
depending on sg_1.

The executor ran in ticket tk_1f7cc0b9 (54.5s, 5 turns, 5 tool calls).
Although venue_search, get_weather, and calculate_cost are marked
parallel_safe=True (they only read fixtures with no side effects), the
executor ran them sequentially — one tool per turn. Timestamps confirm:
venue_search at 22:49:10, get_weather at 22:49:19 (+9s), calculate_cost
at 22:49:29 (+10s). generate_flyer (parallel_safe=False because it
writes workspace/flyer.html) ran at 22:49:43, followed by complete_task.
Parallel execution is permitted but not mandated.

The dataflow integrity check (verify_dataflow in integrity.py) validates
that every fact appearing in flyer.html exists in _TOOL_CALL_LOG output
values — not arguments. This distinction matters: if the LLM fabricated
total_gbp=£9999 and passed it to generate_flyer, verifying against
arguments would falsely confirm it. Verifying against tool outputs
catches the fabrication because 9999 never appears in calculate_cost's
real output (£556 in my run). The flyer template uses data-testid
attributes on every fact (venue_name, venue_address, condition,
temperature_c, total_gbp, deposit_required_gbp) for clean verification.

In sess_2ee7bbbedea2, all 9 flyer facts trace to tool outputs:
"Haymarket Tap" and the Dalry Rd address from venue_search; "cloudy"
and 12°C from get_weather; £556 total and £111 deposit from
calculate_cost. The deposit calculation (556 × 0.20 = 111) follows the
mid-tier rule for totals between £300 and £1000.

## Citations

- sessions/examples/ex5-edinburgh-research/sess_2ee7bbbedea2/logs/trace.jsonl
- sessions/examples/ex5-edinburgh-research/sess_2ee7bbbedea2/logs/tickets/tk_4a282dee/manifest.json (planner)
- sessions/examples/ex5-edinburgh-research/sess_2ee7bbbedea2/logs/tickets/tk_1f7cc0b9/manifest.json (executor)
- sessions/examples/ex5-edinburgh-research/sess_2ee7bbbedea2/workspace/flyer.html