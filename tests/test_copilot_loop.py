"""Exercises the copilot's tool loop with a scripted stand-in for the model (no API key or
network needed). It proves the plumbing: tools run on live data, team changes are visible to
the tools, proposals come back for confirmation. It does NOT test a real model's answers.
Run:  python3 tests/test_copilot_loop.py"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ["COPILOT_PROVIDER"] = "claude"
from growth import copilot

script = [
    [("get_overview", {}), ("query_data", {"table": "checkins", "filters": [{"field": "result", "value": "admitted"}, {"field": "verification", "value": "verified"}, {"field": "person_type", "value": "external"}], "aggregates": [{"op": "count_distinct", "field": "person_id", "as": "visitors"}]})],
    [("query_data", {"table": "people", "group_by": ["college"]}), ("calculate", {"expression": "274000/2050"})],
    [("propose_actions", {"actions": [{"type": "create_task", "title": "Add T-1 reminder for Paid Social registrants", "owner_name": "Arjun Verma", "campaign_id": "C02", "evidence": "show rate 58.6% vs 77.0%"}]})],
    [],
]
seen = []
def fake_step(system, messages):
    assert "Dashboard date" in system
    if messages and isinstance(messages[-1]["content"], list):
        seen.extend(messages[-1]["content"])
    calls = [{"id": f"tu_{len(seen)}_{i}", "name": n, "args": a} for i, (n, a) in enumerate(script.pop(0))]
    content = [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in calls] or [{"type": "text", "text": "done"}]
    return {"role": "assistant", "content": content}, ("" if calls else "done"), calls
copilot._claude_step = fake_step

ov = {"outcomes": [{"id": "O9", "campaign_id": None, "date": "2025-04-13", "verified_checkins": 7}]}
r = copilot.chat({"overlay": ov, "as_of": "2025-04-20", "user_text": "why did we miss?", "events": ["User confirmed proposal P1"]})
assert r["done"] and r["reply"] == "done" and len(r["trace"]) == 5, r
assert r["messages"][0]["content"].startswith("[app event] User confirmed proposal P1")
import json
res = [json.loads(b["content"]) for b in seen]
assert res[0]["metrics"]["unique_external_visitors"] == 2057            # team-logged walk-ins are visible to the tools
assert res[1]["rows"][0]["visitors"] == 2057                            # ad-hoc query agrees with the dashboard metric
assert "does not exist" in res[2]["error"] and seen[2].get("is_error")  # missing field is reported, not invented
assert abs(res[3]["result"] - 133.658) < 0.01
assert r["proposals"][0]["title"].startswith("Add T-1") and "waiting" in res[4]["proposals"][0]["status"]

# guardrails: figures with no tool call are sent back once; an empty answer is sent back once
def scripted(replies):
    log = []
    def step(system, messages):
        log.append(messages[-1]["content"] if isinstance(messages[-1]["content"], str) else "tool results")
        kind, val = replies.pop(0)
        if kind == "call":
            return {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": val, "input": {}}]}, "", [{"id": "t1", "name": val, "args": {}}]
        return {"role": "assistant", "content": [{"type": "text", "text": val or " "}]}, val, []
    copilot._claude_step = step
    return log
log = scripted([("text", "Campus Ambassadors brought 842 visitors."), ("call", "get_campaign_performance"), ("text", "Campus Ambassadors: 390 verified visitors as of 20 Apr.")])
r = copilot.chat({"as_of": "2025-04-20", "user_text": "top source?"})
assert "390" in r["reply"] and "842" not in r["reply"] and log[1].startswith("[app check] Your answer states numbers") and len(r["trace"]) == 1
log = scripted([("text", "The data has no college field, so it cannot answer that.")])
assert copilot.chat({"as_of": "2025-04-20", "user_text": "which college?"})["reply"].startswith("The data has no college")
log = scripted([("call", "get_decisions"), ("text", ""), ("text", "Paid Social is on STOP; the task is waiting for your confirmation.")])
r = copilot.chat({"as_of": "2025-03-20", "user_text": "why stop?"})
assert r["reply"].startswith("Paid Social") and log[2].startswith("[app check] You returned no text")
print("copilot loop checks passed")
