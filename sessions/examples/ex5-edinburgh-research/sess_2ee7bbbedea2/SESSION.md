# Session sess_2ee7bbbedea2

**Scenario:** edinburgh-research
**Created:** 2026-05-22T22:48:44.027600+00:00

## Your task

(The loop half reads this file on every turn. The initial task description
has been written below by the orchestrator when the session was created.
Additional per-session instructions — constraints, identity, voice — can
be added by the scenario author.)

## Task description


You are booking a private event at an Edinburgh pub.

EVENT DETAILS (fixed, use exactly as specified):
- Party size: 6 people
- Date: 2026-04-25 (Saturday)
- Time: 19:30
- Location: near Haymarket station, Edinburgh
- Budget: maximum £800 total

WORKFLOW:
1. First subgoal: Research
   - Call venue_search, get_weather, calculate_cost
   - Store the results
2. Second subgoal: Generate flyer
   - Use the stored results from step 1
   - Call generate_flyer with: venue details from venue_search, weather from get_weather, cost from calculate_cost
   - Call complete_task

YOUR JOB:
1. Find a suitable venue
2. Get the weather forecast
3. Calculate the total cost
4. Generate an HTML flyer with all the details
5. Complete the task

TOOLS AVAILABLE:
- venue_search: find venues by area, party size, and budget
- get_weather: get forecast for a city and date
- calculate_cost: compute total cost for a venue booking
- generate_flyer: create HTML flyer file
- complete_task: mark the task as finished

SUCCESS CRITERIA:
- File workspace/flyer.html exists
- Flyer contains: venue name, address, date, time, party size, weather, cost, deposit

IMPORTANT:
- Use tool outputs for all facts (never invent data)
- Call generate_flyer before complete_task
- All tools except generate_flyer can run in parallel if needed


## Constraints

- Be honest when you do not know something.
- Prefer reading memory over guessing.
- When the task is ambiguous, ask for clarification rather than inventing an answer.
