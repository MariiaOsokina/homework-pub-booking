"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

import json
from pathlib import Path

from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

from starter.edinburgh_research.integrity import (
    _TOOL_CALL_LOG,
    record_tool_call,
)

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


# ---------------------------------------------------------------------------
# 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp

    Returns a ToolResult with:
      output: {"near": ..., "party_size": ..., "results": [<venue dicts>], "count": int}
      summary: "venue_search(<near>, party=<N>): <count> result(s)"

    MUST call record_tool_call(...) before returning so the integrity
    check can see what data was produced.
    """
    arguments = {
        "near": near,
        "party_size": party_size,
        "budget_max_gbp": budget_max_gbp,
    }

    try:
        # Input validation
        if party_size <= 0:
            raise ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message="party_size must be positive",
            )
        if budget_max_gbp < 0:
            raise ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message="budget_max_gbp cannot be negative",
            )

        # Circuit breaker — prevent infinite LLM retry loops.
        # After 3 calls we still run the normal search but flag the
        # summary so the LLM knows to stop retrying.
        prior_calls = sum(1 for r in _TOOL_CALL_LOG if r.tool_name == "venue_search")
        circuit_broken = prior_calls >= 3

        # Load the venues fixture
        fixture_path = _SAMPLE_DATA / "venues.json"

        if not fixture_path.exists():
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"{fixture_path} not found",
            )

        try:
            with open(fixture_path) as f:
                venues = json.load(f)
        except json.JSONDecodeError as e:
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"Invalid JSON in {fixture_path}: {e}",
            ) from e

        # Filter venues based on criteria
        results = []

        for venue in venues:
            venue_area = venue.get("area", "")
            area_match = near.lower() in venue_area.lower()
            is_open = venue.get("open_now", False)
            available_seats = venue.get("seats_available_evening", 0)
            has_capacity = available_seats >= party_size
            hire_fee = venue.get("hire_fee_gbp", 0)
            min_spend = venue.get("min_spend_gbp", 0)
            within_budget = (hire_fee + min_spend) <= budget_max_gbp

            if area_match and is_open and has_capacity and within_budget:
                results.append(venue)

        # Build output
        output = {
            "near": near,
            "party_size": party_size,
            "results": results,
            "count": len(results),
        }

        summary = f"venue_search({near}, party={party_size}): {len(results)} result(s)"
        if circuit_broken:
            summary += (
                f" [CIRCUIT BREAKER: this is call #{prior_calls + 1}. "
                "Stop retrying venue_search and use these results.]"
            )
        result = ToolResult(success=True, output=output, summary=summary)

        # CRITICAL — log for integrity checking
        record_tool_call("venue_search", arguments, result.output)
        return result

    except ToolError:
        raise
    except Exception as e:
        error_result = ToolResult(
            success=False,
            output={"error": str(e)},
            summary=f"venue_search failed: {e}",
        )
        record_tool_call("venue_search", arguments, error_result.output)
        raise ToolError(
            code="SA_TOOL_EXECUTION_FAILED",
            message=f"Unexpected error: {e}",
        ) from e


# ---------------------------------------------------------------------------
# 2- get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD).

    Reads sample_data/weather.json. Returns:
      output: {"city": str, "date": str, "condition": str, "temperature_c": int, ...}
      summary: "get_weather(<city>, <date>): <condition>, <temp>C"

    If the city or date is not in the fixture, return success=False with
    a clear error message. Do NOT raise for invalid inputs.

    MUST call record_tool_call(...) before returning.
    """
    arguments = {"city": city, "date": date}

    try:
        # Load weather fixture
        weather_file = _SAMPLE_DATA / "weather.json"

        # Dependency failures: RAISE (environment problem, not input problem)
        if not weather_file.exists():
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"Weather fixture not found: {weather_file}",
            )

        try:
            with open(weather_file) as f:
                weather_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING", message=f"Invalid JSON in {weather_file}: {e}"
            ) from e

        # Input validation: RETURN FALSE (LLM can retry with different inputs)
        city_lower = city.lower()

        if city_lower not in weather_data:
            result = ToolResult(
                success=False,
                output={"error": "city_not_found", "city": city},
                summary=f"get_weather({city}, {date}): City not found",
            )
            record_tool_call("get_weather", arguments, result.output)
            return result

        city_forecasts = weather_data[city_lower]

        if date not in city_forecasts:
            result = ToolResult(
                success=False,
                output={"error": "date_not_found", "city": city, "date": date},
                summary=f"get_weather({city}, {date}): Date not found",
            )
            record_tool_call("get_weather", arguments, result.output)
            return result

        forecast = city_forecasts[date]

        # Build output
        output = {
            "city": city,
            "date": date,
            "condition": forecast.get("condition", "unknown"),
            "temperature_c": forecast.get("temperature_c", 0),
            "precip_mm": forecast.get("precip_mm", 0.0),
            "wind_kph": forecast.get("wind_kph", 0),
        }

        # Factual summary only - no instructions
        summary = f"get_weather({city}, {date}): {output['condition']}, {output['temperature_c']}C"

        result = ToolResult(success=True, output=output, summary=summary)
        record_tool_call("get_weather", arguments, result.output)

        return result

    except ToolError:
        # Re-raise ToolErrors (framework will handle them)
        raise
    except Exception as e:
        # Unexpected errors: log and raise
        error_result = ToolResult(
            success=False, output={"error": str(e)}, summary=f"get_weather failed: {str(e)}"
        )
        record_tool_call("get_weather", arguments, error_result.output)
        raise ToolError(
            code="SA_TOOL_EXECUTION_FAILED", message=f"Unexpected error in get_weather: {e}"
        ) from e


# # ---------------------------------------------------------------------------
# # 3 — calculate_cost
# # ---------------------------------------------------------------------------


def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking.
    Formula:
      base_per_head = base_rates_gbp_per_head[catering_tier]
      venue_mult    = venue_modifiers[venue_id]
      subtotal      = base_per_head * venue_mult * party_size * max(1, duration_hours)
      service       = subtotal * service_charge_percent / 100
      total         = subtotal + service + <venue's hire_fee_gbp + min_spend_gbp>
      deposit_rule  = per deposit_policy thresholds

    Returns:
      output: {
        "venue_id": str,
        "party_size": int,
        "duration_hours": int,
        "catering_tier": str,
        "subtotal_gbp": int,
        "service_gbp": int,
        "total_gbp": int,
        "deposit_required_gbp": int,
      }
      summary: "calculate_cost(<venue>, <party>): total £<N>, deposit £<M>"

    MUST call record_tool_call(...) before returning.
    """
    arguments = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }

    try:
        # Load fixtures - raise on dependency failures
        catering_path = _SAMPLE_DATA / "catering.json"
        venues_path = _SAMPLE_DATA / "venues.json"

        if not catering_path.exists():
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"Catering fixture not found: {catering_path}",
            )
        if not venues_path.exists():
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING",
                message=f"Venues fixture not found: {venues_path}",
            )

        try:
            with open(catering_path) as f:
                catering = json.load(f)
            with open(venues_path) as f:
                venues = json.load(f)
        except json.JSONDecodeError as e:
            raise ToolError(
                code="SA_TOOL_DEPENDENCY_MISSING", message=f"Invalid JSON in fixtures: {e}"
            ) from e

        # Input validation - return False for invalid inputs
        venue = next((v for v in venues if v["id"] == venue_id), None)
        if not venue:
            result = ToolResult(
                success=False,
                output={"error": "venue_not_found", "venue_id": venue_id},
                summary=f"calculate_cost: Venue '{venue_id}' not found",
            )
            record_tool_call("calculate_cost", arguments, result.output)
            return result

        if catering_tier not in catering["base_rates_gbp_per_head"]:
            result = ToolResult(
                success=False,
                output={"error": "invalid_tier", "catering_tier": catering_tier},
                summary=f"calculate_cost: Invalid catering tier '{catering_tier}'",
            )
            record_tool_call("calculate_cost", arguments, result.output)
            return result

        # Calculation logic
        base_per_head = catering["base_rates_gbp_per_head"][catering_tier]
        venue_mult = catering["venue_modifiers"].get(venue_id, 1.0)
        service_charge_percent = catering["service_charge_percent"]

        subtotal = base_per_head * venue_mult * party_size * max(1, duration_hours)
        service_gbp = subtotal * (service_charge_percent / 100)
        venue_fees = venue.get("hire_fee_gbp", 0) + venue.get("min_spend_gbp", 0)
        total_gbp = subtotal + service_gbp + venue_fees

        # Deposit policy
        if total_gbp < 300:
            deposit_required_gbp = 0
        elif total_gbp <= 1000:
            deposit_required_gbp = int(total_gbp * 0.20)
        else:
            deposit_required_gbp = int(total_gbp * 0.30)

        # Build output
        output = {
            "venue_id": venue_id,
            "party_size": party_size,
            "duration_hours": duration_hours,
            "catering_tier": catering_tier,
            "subtotal_gbp": int(subtotal),
            "service_gbp": int(service_gbp),
            "total_gbp": int(total_gbp),
            "deposit_required_gbp": deposit_required_gbp,
        }

        # Factual summary only
        summary = f"calculate_cost({venue_id}, party={party_size}): total £{output['total_gbp']}, deposit £{output['deposit_required_gbp']}"

        result = ToolResult(success=True, output=output, summary=summary)
        record_tool_call("calculate_cost", arguments, result.output)

        return result

    except ToolError:
        raise  # Re-raise ToolErrors
    except Exception as e:
        # Unexpected errors: log and raise
        error_result = ToolResult(
            success=False, output={"error": str(e)}, summary=f"calculate_cost failed: {str(e)}"
        )
        record_tool_call("calculate_cost", arguments, error_result.output)
        raise ToolError(
            code="SA_TOOL_EXECUTION_FAILED", message=f"Unexpected error in calculate_cost: {e}"
        ) from e


def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html."""

    arguments = {"event_details": event_details}

    # Strict validation - reject missing keys
    required_keys = [
        "venue_name",
        "venue_address",
        "date",
        "time",
        "party_size",
        "condition",
        "temperature_c",
        "total_gbp",
        "deposit_required_gbp",
    ]

    missing_keys = [key for key in required_keys if key not in event_details]

    if missing_keys:
        # error_msg = f"Missing required keys: {missing_keys}. Fix inputs and retry."
        error_result = ToolResult(
            success=False,
            output={"error": "missing_keys", "keys": missing_keys},
            summary=f"generate_flyer failed: missing {missing_keys}",
        )
        record_tool_call("generate_flyer", arguments, error_result.output)
        return error_result

    try:
        # Extract values
        venue_name = event_details["venue_name"]
        venue_address = event_details["venue_address"]
        date = event_details["date"]
        time = event_details["time"]
        party_size = event_details["party_size"]
        condition = event_details["condition"]
        temperature_c = event_details["temperature_c"]
        total_gbp = event_details["total_gbp"]
        deposit_required_gbp = event_details["deposit_required_gbp"]

        # Generate HTML flyer (unchanged)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Event Flyer - {venue_name}</title>
    <style>
        :root {{
            --primary: #e54676;
            --bg: #236d62;
            --card: #ffffff;
            --text: #64338b;
            --muted: #64748b;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            padding: 40px 20px;
            min-height: 100vh;
            display: flex;
            justify-content: center;
        }}
        .flyer {{
            width: 100%; max-width: 600px;
            background: var(--card);
            border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            overflow: hidden;
        }}
        .header {{
            background: var(--primary);
            color: white;
            padding: 48px 30px;
            text-align: center;
        }}
        .header h1 {{ font-family: serif; font-size: 2.8em; margin-bottom: 8px; }}
        .subtitle {{ font-size: 1.1em; letter-spacing: 2px; text-transform: uppercase; opacity: 0.9; }}
        .content {{ padding: 30px; }}
        .group {{ margin-bottom: 25px; }}
        .group-title {{ font-size: 0.85em; color: var(--primary); font-weight: 800; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px; }}
        .item {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f5f9; }}
        .label {{ color: var(--muted); }}
        .value {{ font-weight: 600; color: var(--text); }}
        .weather-badge {{
            padding: 4px 12px; background: #e0e7ff; color: #4338ca;
            border-radius: 6px; font-weight: bold; font-size: 0.9em;
        }}
        .cost-box {{
            background: #f8fafc; padding: 20px; border-radius: 12px;
            border: 1px solid #e2e8f0; margin-top: 20px;
        }}
        .total {{ font-size: 1.5em; font-weight: 800; color: var(--primary); display: flex; justify-content: space-between; }}
        .footer {{ padding: 20px; text-align: center; color: var(--muted); font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="flyer">
        <div class="header">
            <h1 data-testid="venue_name">{venue_name}</h1>
            <p class="subtitle">Join us for a private event</p>
        </div>
        <div class="content">
            <div class="group">
                <div class="group-title">When &amp; Where</div>
                <div class="item"><span class="label">Date</span><span class="value" data-testid="date">{date}</span></div>
                <div class="item"><span class="label">Time</span><span class="value" data-testid="time">{time}</span></div>
                <div class="item"><span class="label">Guests</span><span class="value" data-testid="party_size">{party_size}</span></div>
                <div class="item"><span class="label">Address</span><span class="value" data-testid="venue_address">{venue_address}</span></div>
            </div>
            <div class="group">
                <div class="group-title">Weather Forecast</div>
                <div class="item">
                    <span class="label">Conditions</span>
                    <span class="weather-badge" data-testid="condition">{condition}</span>
                </div>
                <div class="item">
                    <span class="label">Temp</span>
                    <span class="value" data-testid="temperature_c">{temperature_c}\u00b0C</span>
                </div>
            </div>
            <div class="cost-box">
                <div class="total">
                    <span>Total</span>
                    <span data-testid="total_gbp">\u00a3{total_gbp}</span>
                </div>
                <div class="item" style="border:none; margin-top:5px;">
                    <span class="label">Deposit Required</span>
                    <span class="value" data-testid="deposit_required_gbp">\u00a3{deposit_required_gbp}</span>
                </div>
            </div>
        </div>
        <div class="footer">Looking forward to seeing you there!</div>
    </div>
</body>
</html>
"""
        # Write to file
        workspace_dir = session.directory / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        path = workspace_dir / "flyer.html"
        path.write_text(html_content, encoding="utf-8")

        bytes_written = len(html_content.encode("utf-8"))

        # Output and record
        output = {"path": "workspace/flyer.html", "bytes_written": bytes_written}
        summary = f"generate_flyer: wrote workspace/flyer.html ({bytes_written} bytes)"

        result = ToolResult(success=True, output=output, summary=summary)
        record_tool_call("generate_flyer", arguments, result.output)

        return result

    except OSError as e:
        # File system errors - raise
        error_result = ToolResult(
            success=False,
            output={"error": "filesystem_error", "details": str(e)},
            summary="generate_flyer: File system error",
        )
        record_tool_call("generate_flyer", arguments, error_result.output)
        raise ToolError(
            code="SA_TOOL_EXECUTION_FAILED", message=f"Failed to write flyer.html: {e}"
        ) from e

    except Exception as e:
        # Unexpected errors - raise
        error_result = ToolResult(
            success=False, output={"error": str(e)}, summary=f"generate_flyer failed: {str(e)}"
        )
        record_tool_call("generate_flyer", arguments, error_result.output)
        raise ToolError(
            code="SA_TOOL_EXECUTION_FAILED", message=f"Unexpected error in generate_flyer: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="""Search Edinburgh venues by area, party size, and budget.

Returns venues that match ALL criteria:
- Area contains the search term (case-insensitive)
- Currently open (open_now=true)
- Available evening seats >= party_size
- Total cost (hire_fee + min_spend) <= budget

Returns a list of matching venue objects with full details.""",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {
                        "type": "string",
                        "description": "Area to search (e.g., 'Haymarket', 'Old Town')",
                    },
                    "party_size": {"type": "integer", "description": "Number of guests"},
                    "budget_max_gbp": {
                        "type": "integer",
                        "default": 1000,
                        "description": "Maximum total cost in GBP",
                    },
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {
                        "count": 1,
                        "results": [{"id": "haymarket_tap", "name": "Haymarket Tap"}],
                    },
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get weather forecast for a city on a specific date (YYYY-MM-DD format).",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="""Calculate total booking cost and required deposit.

Computes:
- Catering cost per person (varies by tier and venue)
- Service charge
- Venue fees (hire fee + minimum spend)
- Required deposit (based on total)

Returns breakdown with total and deposit amounts.""",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {
                        "type": "string",
                        "description": "Venue identifier from venue_search",
                    },
                    "party_size": {"type": "integer", "description": "Number of guests"},
                    "duration_hours": {"type": "integer", "description": "Event duration in hours"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                        "description": "Catering level",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                        "catering_tier": "bar_snacks",
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description="""Generate HTML flyer and save to workspace/flyer.html.

Requires event_details dict with:
- venue_name, venue_address, date, time, party_size
- condition, temperature_c (from weather)
- total_gbp, deposit_required_gbp (from cost calculation)

Creates styled HTML flyer with all event information.""",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {
                    "event_details": {
                        "type": "object",
                        "description": "Dict containing all event information",
                    }
                },
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "venue_address": "123 Main St",
                            "date": "2026-04-25",
                            "time": "19:30",
                            "party_size": 6,
                            "condition": "cloudy",
                            "temperature_c": 12,
                            "total_gbp": 540,
                            "deposit_required_gbp": 0,
                        }
                    },
                    "output": {"path": "workspace/flyer.html", "bytes_written": 3245},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
