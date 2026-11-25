"""Embedded AI growth analyst.

The model never sees raw tables and never does its own arithmetic on memory: it calls the
tools below, which run on the same engine (and the same saved team changes) as the
dashboard. Actions (tasks, campaign changes) are only *proposed*; the browser shows a
confirmation card and applies them when the user clicks Confirm.

Providers, chosen by environment:
  ANTHROPIC_API_KEY  -> Claude through the official `anthropic` SDK   (default)
  GEMINI_API_KEY     -> Google Gemini REST API (free tier works)
  neither            -> a small rule-based analyst that only handles common questions
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from .engine import DEFINITIONS, TABLE_DOCS, Model, calculate

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MAX_STEPS = 10
TIME_BUDGET_S = 40  # return to the browser before serverless timeouts; it resumes the turn

AS_OF = {"type": "string", "description": "Snapshot day YYYY-MM-DD (end of day IST). Omit to use the date selected on the dashboard."}

TOOLS = [
    {"name": "get_overview",
     "description": "Whole-event funnel as of a date: anonymous event counts, identified/registered/confirmed/visitor head-counts, rates, spend, active targets with gaps, budget remaining and the forecast (with its assumptions). Start here for 'how are we doing' questions.",
     "input_schema": {"type": "object", "properties": {"as_of": AS_OF}}},
    {"name": "get_campaign_performance",
     "description": "The same funnel metrics per campaign (plus an 'Unattributed (walk-ins)' row). Use `since` to restrict flow metrics to a window, e.g. the last 14 days, to compare periods.",
     "input_schema": {"type": "object", "properties": {"as_of": AS_OF, "since": {"type": "string", "description": "Optional first day of the window, YYYY-MM-DD inclusive."}}}},
    {"name": "get_decisions",
     "description": "Scale / fix / stop verdict for every campaign from the team's explicit thresholds, with the evidence behind each verdict, remaining budget and a budget reallocation estimate (with its assumption).",
     "input_schema": {"type": "object", "properties": {"as_of": AS_OF}}},
    {"name": "get_time_series",
     "description": "Daily or weekly new and cumulative identified people, registrations, verified visitors, spend, sessions, clicks, impressions; plus the goal active on each day. Use for trends, pace and 'what changed' questions.",
     "input_schema": {"type": "object", "properties": {"as_of": AS_OF, "campaign_id": {"type": "string", "description": "e.g. C02. Omit for all campaigns."},
                                                        "interval": {"type": "string", "enum": ["day", "week"]},
                                                        "from": {"type": "string", "description": "Optional first day YYYY-MM-DD."}}}},
    {"name": "query_data",
     "description": "Ad-hoc query over one table for anything the other tools do not cover: filter, group, aggregate, sort. Rows later than the as-of date are never returned. "
                    "Group-by and filter fields may be wrapped as date(f), week(f), month(f), hour(f), weekday(f). An unknown field returns an error listing the real fields: "
                    "if what you need is not there, the data cannot answer. Tables and fields:\n" + "\n".join(f"- {k}: {v}" for k, v in TABLE_DOCS.items()),
     "input_schema": {"type": "object", "required": ["table"], "properties": {
         "table": {"type": "string", "enum": list(TABLE_DOCS)},
         "filters": {"type": "array", "items": {"type": "object", "required": ["field"], "properties": {
             "field": {"type": "string"},
             "op": {"type": "string", "enum": ["eq", "ne", "in", "not_in", "contains", "gt", "gte", "lt", "lte", "is_null", "not_null"]},
             "value": {"description": "String, number, boolean, or an array for in / not_in."}}}},
         "group_by": {"type": "array", "items": {"type": "string"}},
         "aggregates": {"type": "array", "items": {"type": "object", "required": ["op"], "properties": {
             "op": {"type": "string", "enum": ["count", "count_distinct", "sum", "avg", "min", "max"]},
             "field": {"type": "string"}, "as": {"type": "string"}}}},
         "select": {"type": "array", "items": {"type": "string"}, "description": "Columns to return when not aggregating."},
         "order_by": {"type": "array", "items": {"type": "object", "properties": {"field": {"type": "string"}, "dir": {"type": "string", "enum": ["asc", "desc"]}}}},
         "limit": {"type": "integer", "description": "Default 50, max 200."},
         "as_of": AS_OF}}},
    {"name": "calculate",
     "description": "Evaluate an arithmetic expression exactly, e.g. '(93000-59000)/340*100'. Use it for every derived number you report that a tool did not return directly.",
     "input_schema": {"type": "object", "required": ["expression"], "properties": {"expression": {"type": "string"}}}},
    {"name": "propose_actions",
     "description": "Propose changes in the management tool. Nothing is saved until the user clicks Confirm on the card the app shows; you will be told the outcome in a later '[app event]' line. "
                    "Use when the user asks to create/assign/update something, or when your analysis ends in a concrete next step they agreed to.",
     "input_schema": {"type": "object", "required": ["actions"], "properties": {"actions": {"type": "array", "items": {"type": "object", "required": ["type"], "properties": {
         "type": {"type": "string", "enum": ["create_task", "update_task", "update_campaign"]},
         "title": {"type": "string"}, "description": {"type": "string"},
         "owner_name": {"type": "string", "description": "Must be one of the team members."},
         "due_date": {"type": "string", "description": "YYYY-MM-DD"},
         "priority": {"type": "string", "enum": ["high", "medium", "low"]},
         "campaign_id": {"type": "string"},
         "task_id": {"type": "string", "description": "For update_task."},
         "status": {"type": "string", "description": "Task: todo|in_progress|blocked|done. Campaign: active|paused|scaled|stopped|planned."},
         "budget_inr": {"type": "number", "description": "For update_campaign."},
         "evidence": {"type": "string", "description": "The numbers (with as-of date) that justify this action."}}}}}}},
]


def system_prompt(model: Model, as_of: str, team: list[str]) -> str:
    camps = "; ".join(f"{c['campaign_id']}={c['campaign_name']} ({c.get('channel')}, owner {c.get('owner_name')}, status {c.get('status')})" for c in model.campaigns)
    defs = "\n".join(f"- {k}: {v}" for k, v in DEFINITIONS.items())
    return f"""You are the growth analyst built into the Growth Center, the command center a college-festival team uses to grow ATTENDANCE for {model.event['event_name']} (event days {model.event_start} to {model.event_end}, IST, currency INR). You help the team understand performance, find problems, decide what to scale, change or stop, and turn decisions into tracked tasks.

Dashboard date ("today" for the team): {as_of}. Data history runs {model.history_start} to {model.default_as_of()}. Tools default to the dashboard date and never return anything later than the date asked for.
Campaigns: {camps}
Team members (valid task owners): {', '.join(team)}

How you work
- Every number you state must come from a tool call made in this conversation, or from `calculate` applied to tool results. Never use outside benchmarks, typical industry rates or remembered figures as if they were this team's data. The data changes between questions (the team edits it), so re-query instead of reusing numbers from earlier turns when the question depends on current values.
- State the as-of date and the metric definition whenever it matters (for example "2,050 verified external visitors as of 20 Apr").
- Separate three things explicitly when you explain or recommend: what the data shows (evidence), what you are inferring, and what is an assumption. The forecast's show rate and the reallocation estimate are assumptions; say so.
- The data records a source relationship between campaigns and registrations. It does not prove a campaign caused attendance, and it cannot tell you what would have happened without the campaign.
- If the data cannot answer, say so plainly, say what is missing, and offer the closest thing the data can answer. Things this dataset does not contain: demographics, college or city of a person, ticket price or revenue, unique (de-duplicated) reach, creative- or ad-level results, cost of an individual person, satisfaction, weather, competitor events, sponsor data, anything after the last history day. Do not guess them.
- Recommendations name the campaign, the action, the supporting numbers and what would change your mind.
- To create or change tasks or campaigns, call `propose_actions`. Then tell the user the proposal is waiting for their confirmation. Never say something was created or changed unless an "[app event]" line says the user confirmed it.
- Be concise: lead with the answer, then the few numbers that support it. Short paragraphs or a small table. No preamble.

Counting rules already applied by the tools (apply them yourself in query_data)
- Head-counts are EXTERNAL people only (person_type = external); internal, staff and test identities are excluded from goals.
- Import-retry duplicates are already removed. Registration status is the latest version on the date.
- An actual visitor needs a check-in with result=admitted AND verification=verified; count distinct person_id, since one person can have several admission records.
- impressions, clicks, sessions, registration_starts and reach are anonymous event counts, not people; summed reach is not unique reach.
- Campaign attribution is the campaign on the registration; walk-ins are unattributed.

Metric definitions
{defs}"""


def run_tool(model: Model, as_of: str, name: str, args: dict, proposals: list) -> dict:
    args = args or {}
    a = (args.get("as_of") or as_of)[:10]
    try:
        if name == "get_overview":
            o = model.overview(a)
            o.pop("definitions", None)
            return o
        if name == "get_campaign_performance":
            return {"as_of": a, "since": args.get("since"), "campaigns": model.campaign_table(a, args.get("since")),
                    "all_campaigns_total": model.metrics(a, args.get("since"))}
        if name == "get_decisions":
            return model.decisions(a)
        if name == "get_time_series":
            ts = model.time_series(a, args.get("campaign_id") or "__all__")
            if args.get("from"):
                ts = [r for r in ts if r["date"] >= args["from"][:10]]
            if (args.get("interval") or ("week" if len(ts) > 45 else "day")) == "week":
                import datetime as dt
                weeks = {}
                for r in ts:
                    d = dt.date.fromisoformat(r["date"])
                    k = (d - dt.timedelta(days=d.weekday())).isoformat()
                    w = weeks.setdefault(k, {"week_starting": k, **{f: 0 for f in ("identified", "registrations", "visitors", "spend_inr", "sessions", "clicks", "impressions")}})
                    for f in ("identified", "registrations", "visitors", "spend_inr", "sessions", "clicks", "impressions"):
                        w[f] += r[f]
                    for f in ("cum_identified", "cum_registrations", "cum_visitors", "cum_spend_inr", "registration_goal", "visitor_goal", "budget_inr"):
                        w[f] = r[f]
                return {"as_of": a, "interval": "week (Mon-Sun; first/last week may be partial)", "rows": list(weeks.values())}
            return {"as_of": a, "interval": "day", "rows": ts[-120:]}
        if name == "query_data":
            return model.query(args, a)
        if name == "calculate":
            return {"expression": args.get("expression"), "result": calculate(str(args.get("expression", "")))}
        if name == "propose_actions":
            out = []
            for act in args.get("actions") or []:
                act = {k: v for k, v in act.items() if v not in (None, "")}
                if act.get("campaign_id") and act["campaign_id"] not in model.camp:
                    out.append({"error": f"Unknown campaign_id {act['campaign_id']}"})
                    continue
                if act.get("type") == "update_task" and act.get("task_id") not in {t.get("task_id") for t in model.tasks}:
                    out.append({"error": f"Unknown task_id {act.get('task_id')}"})
                    continue
                act["proposal_id"] = f"P{int(time.time()*1000) % 10**8}-{len(proposals)+1}"
                proposals.append(act)
                out.append({"proposal_id": act["proposal_id"], "status": "shown to user, waiting for their confirmation"})
            return {"proposals": out}
        return {"error": f"Unknown tool {name}"}
    except Exception as e:  # tool errors go back to the model so it can correct itself
        return {"error": f"{type(e).__name__}: {e}"}


def _trace(name, args, result):
    if "error" in result:
        s = "error: " + str(result["error"])[:160]
    elif name == "query_data":
        s = f"{result.get('rows_matched')} rows matched, {result.get('rows_returned')} returned"
    elif name == "calculate":
        s = f"= {result.get('result')}"
    elif name == "propose_actions":
        s = f"{len(result.get('proposals', []))} action(s) proposed"
    else:
        s = f"as of {result.get('as_of', '')}"
    return {"tool": name, "input": args, "summary": s}


# ---------------------------------------------------------------------------- Claude
def _claude_step(system, messages):
    import anthropic

    client = anthropic.Anthropic()
    kwargs = dict(model=CLAUDE_MODEL, max_tokens=16000, system=system, tools=TOOLS, messages=messages,
                  thinking={"type": "adaptive"}, output_config={"effort": "medium"})
    try:
        # Server-side refusal fallback (beta). If this SDK/model combination rejects it, use the plain call.
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except (TypeError, anthropic.BadRequestError, anthropic.NotFoundError):
        resp = client.messages.create(**kwargs)
    content = resp.model_dump(mode="json", exclude_none=True)["content"]
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in content if b.get("type") == "tool_use"]
    if resp.stop_reason == "refusal":
        text = text or "The model declined to answer this request."
    if resp.stop_reason == "max_tokens" and not calls:
        text += "\n\n(The answer was cut off at the length limit.)"
    return {"role": "assistant", "content": content}, text, calls


def _claude_results(calls, results):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(r, ensure_ascii=False, default=str),
                                         **({"is_error": True} if "error" in r else {})} for c, r in zip(calls, results)]}


# ---------------------------------------------------------------------------- Gemini
def _gemini_schema(s):
    if not isinstance(s, dict):
        return s
    out = {}
    for k, v in s.items():
        if k == "type":
            out[k] = str(v).upper()
        elif k == "properties":
            out[k] = {pk: _gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _gemini_schema(v)
        elif k in ("description", "enum", "required"):
            out[k] = v
    if "type" not in out:
        out["type"] = "STRING"
    if out["type"] == "OBJECT" and not out.get("properties"):
        out.pop("properties", None)
    return out


_GEMINI = {"model": GEMINI_MODEL, "others": None}  # the model that last worked, and alternatives discovered from the API


def _gemini_post(model, body):
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def _gemini_alternatives():
    """Other text models this key can call, 'flash' models first. Used when the configured one is retired or busy."""
    if _GEMINI["others"] is None:
        try:
            req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
            with urllib.request.urlopen(req, timeout=30) as r:
                models = json.loads(r.read()).get("models", [])
            names = [m["name"].split("/", 1)[-1] for m in models if "generateContent" in (m.get("supportedGenerationMethods") or [])]
            skip = ("image", "tts", "audio", "embedding", "live", "vision", "robotics", "computer", "learnlm", "gemma", "nano")
            names = [n for n in names if n.startswith("gemini") and not any(w in n for w in skip)]
            _GEMINI["others"] = sorted(names, key=lambda n: ("flash" not in n, "lite" in n, "preview" in n or "exp" in n, [-ord(ch) for ch in n]))
        except Exception:
            _GEMINI["others"] = []
    return [n for n in _GEMINI["others"] if n != _GEMINI["model"]]


def _gemini_step(system, messages):
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": messages,
            "tools": [{"functionDeclarations": [{"name": t["name"], "description": t["description"], "parameters": _gemini_schema(t["input_schema"])} for t in TOOLS]}]}
    data, last, tried = None, "", []
    candidates = [_GEMINI["model"]]
    for model in candidates:
        for attempt in range(2):  # the free tier often answers 503 (busy) or 429 (rate limit): wait once, then try another model
            try:
                data = _gemini_post(model, body)
                break
            except urllib.error.HTTPError as e:
                last = f"Gemini API error {e.code} on {model}: {e.read().decode(errors='replace')[:300]}"
                tried.append(f"{model}: {e.code}")
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(2)
                    continue
                if e.code not in (404, 429, 500, 503):
                    raise RuntimeError(last)
                break
        if data is not None:
            _GEMINI["model"] = model
            break
        if len(candidates) == 1:
            candidates += _gemini_alternatives()[:6]
    if data is None:
        raise RuntimeError("The Gemini models are busy (503) or over this key's quota (429) right now. Wait a minute and send the question again. Tried " + "; ".join(dict.fromkeys(tried)))
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
    calls = [{"id": None, "name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}} for p in parts if "functionCall" in p]
    if not parts:
        text = f"The model returned no answer (finish reason: {cand.get('finishReason', 'unknown')})."
    return {"role": "model", "parts": parts or [{"text": text}]}, text, calls  # parts returned verbatim (keeps thought signatures)


def gemini_check() -> dict:
    """Diagnostic: which Gemini models this key can list, and whether a one-word request to each candidate succeeds."""
    if not os.environ.get("GEMINI_API_KEY"):
        return {"error": "GEMINI_API_KEY is not set"}
    _GEMINI["others"] = None
    names = [GEMINI_MODEL] + [n for n in _gemini_alternatives() if n != GEMINI_MODEL]
    out = []
    for n in names[:10]:
        try:
            _gemini_post(n, {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}]})
            out.append({"model": n, "status": 200})
        except urllib.error.HTTPError as e:
            out.append({"model": n, "status": e.code, "detail": e.read().decode(errors="replace")[:160]})
        except Exception as e:
            out.append({"model": n, "status": type(e).__name__})
    return {"configured": GEMINI_MODEL, "in_use": _GEMINI["model"], "listed": _GEMINI["others"], "probe": out}


def _gemini_results(calls, results):
    return {"role": "user", "parts": [{"functionResponse": {"name": c["name"], "response": r}} for c, r in zip(calls, results)]}


# ---------------------------------------------------------------------------- entry point
def provider_name() -> str:
    forced = os.environ.get("COPILOT_PROVIDER")
    if forced:
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "offline"


def chat(payload: dict) -> dict:
    """One browser round trip. payload: overlay, as_of, team, provider, messages (provider-native
    history kept by the browser), user_text, events."""
    model = Model(payload.get("overlay"))
    as_of = model.clamp(payload.get("as_of"))
    team = payload.get("team") or sorted({c.get("owner_name") for c in model.campaigns if c.get("owner_name")})
    provider = provider_name()
    messages = list(payload.get("messages") or []) if payload.get("provider") == provider else []
    text = (payload.get("user_text") or "").strip()
    events = [e for e in (payload.get("events") or []) if e]
    if events:
        text = "\n".join(f"[app event] {e}" for e in events) + ("\n\n" + text if text else "")
    proposals, trace = [], []

    if provider == "offline":
        reply = offline_answer(model, as_of, payload.get("user_text") or "", proposals, trace, team)
        return {"provider": provider, "messages": [], "done": True, "reply": reply, "proposals": proposals, "trace": trace,
                "notice": "No AI key is configured on the server, so this is the built-in rule-based analyst. Set ANTHROPIC_API_KEY or GEMINI_API_KEY for the full copilot."}

    step, results_msg = (_claude_step, _claude_results) if provider == "claude" else (_gemini_step, _gemini_results)
    if text:
        messages.append({"role": "user", "content": text} if provider == "claude" else {"role": "user", "parts": [{"text": text}]})
    system = system_prompt(model, as_of, team)
    start = time.time()
    try:
        for _ in range(MAX_STEPS):
            msg, reply, calls = step(system, messages)
            messages.append(msg)
            if not calls:
                return {"provider": provider, "messages": messages, "done": True, "reply": reply, "proposals": proposals, "trace": trace}
            results = []
            for c in calls:
                r = run_tool(model, as_of, c["name"], c["args"], proposals)
                results.append(r)
                trace.append(_trace(c["name"], c["args"], r))
            messages.append(results_msg(calls, results))
            if time.time() - start > TIME_BUDGET_S:
                return {"provider": provider, "messages": messages, "done": False, "reply": "", "proposals": proposals, "trace": trace}
        return {"provider": provider, "messages": messages, "done": False, "reply": "", "proposals": proposals, "trace": trace}
    except Exception as e:
        return {"provider": provider, "messages": payload.get("messages") or [], "done": True, "error": _friendly(e), "proposals": proposals, "trace": trace}


def _friendly(e: Exception) -> str:
    try:
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            return "The AI provider rejected the API key. Check ANTHROPIC_API_KEY on the server."
        if isinstance(e, anthropic.RateLimitError):
            return "The AI provider is rate-limiting requests. Wait a few seconds and try again."
        if isinstance(e, anthropic.APIStatusError):
            return f"AI provider error {e.status_code}: {str(e)[:300]}"
        if isinstance(e, anthropic.APIConnectionError):
            return "Could not reach the AI provider. Check the server's network connection."
    except ImportError:
        if isinstance(e, ImportError) or "anthropic" in str(e):
            return "The `anthropic` package is not installed on the server. Run: pip install -r requirements.txt"
    if isinstance(e, ModuleNotFoundError):
        return "The `anthropic` package is not installed on the server. Run: pip install -r requirements.txt"
    return f"{type(e).__name__}: {str(e)[:400]}"


# ---------------------------------------------------------------------------- offline analyst
def _inr(v):
    return "n/a" if v is None else f"₹{v:,.0f}"


def _pct(v):
    return "n/a" if v is None else f"{v:.1%}"


def offline_answer(model: Model, as_of: str, q: str, proposals: list, trace: list, team: list[str]) -> str:
    """Rule-based fallback. It routes a question to the same tools the AI uses and reports their
    numbers; anything it cannot route, it declines instead of guessing."""
    ql = q.lower()
    m = re.search(r"(20\d\d-\d\d-\d\d)", q)
    if m:
        as_of = model.clamp(m.group(1))

    def use(name, args=None):
        r = run_tool(model, as_of, name, args or {}, proposals)
        trace.append(_trace(name, args or {}, r))
        return r

    missing = [w for w in ("age", "gender", "college", "city", "revenue", "ticket", "price", "nps", "satisfaction", "weather", "sponsor", "demographic",
                           "creative", "unique reach", "why did", "cause", "next year", "competitor") if re.search(rf"\b{w}", ql)]
    if missing:
        return (f"The data can't answer that: it has no information on {', '.join(missing)}. It records campaigns, daily anonymous activity and spend, identified people, "
                "engagement events, registrations with status history, check-ins, targets and tasks. Ask me about those and I'll give you exact numbers.")
    camp = next((c for c in model.campaigns if c["campaign_name"].lower() in ql or re.search(rf"\b{c['campaign_id'].lower()}\b", ql)), None)
    if re.search(r"\b(create|add|make|assign)\b.*\btask\b", ql):
        title = re.sub(r"^.*?\btask\b\s*(to|for|:)?\s*", "", q, flags=re.I).strip().rstrip(".") or "Follow up"
        owner = next((t for t in team if t.split()[0].lower() in ql), (camp or {}).get("owner_name") or team[0])
        use("propose_actions", {"actions": [{"type": "create_task", "title": title[:90], "owner_name": owner, "priority": "medium",
                                             "campaign_id": (camp or {}).get("campaign_id"), "evidence": f"Requested in chat on dashboard date {as_of}."}]})
        return f"I drafted the task \"{title[:90]}\" for {owner}. Confirm it on the card below to save it."
    if any(w in ql for w in ("task", "overdue", "deadline", "action item")):
        r = use("query_data", {"table": "tasks", "limit": 200})
        rows = r["rows"]
        od = [t for t in rows if t["overdue"]]
        open_ = [t for t in rows if t.get("status") != "done"]
        lines = [f"{len(rows)} tasks: {len(open_)} open, {len(od)} overdue as of {as_of}."]
        lines += [f"- OVERDUE {t['due_date']}: {t['title']} ({t.get('owner_name')}, {t.get('status')})" for t in od[:8]]
        return "\n".join(lines)
    if any(w in ql for w in ("scale", "stop", "cut", "pause", "prioriti", "recommend", "should we", "reallocat", "double down", "underperform", "worst", "best", "decide")):
        d = use("get_decisions")
        lines = [f"Verdicts as of {as_of}, judged on {d['cost_metric']} over the {d['basis']} (blended {_inr(d['blended_cost'])}):"]
        for c in d["campaigns"]:
            if camp and c["campaign_id"] != camp["campaign_id"]:
                continue
            lines.append(f"- {c['campaign_name']}: {c['verdict']}. {c['action']} Evidence: {'; '.join(c['evidence']) or 'near blended on all checks'}")
        if d["reallocation"]:
            ra = d["reallocation"]
            lines.append(f"Reallocation estimate: moving {_inr(ra['amount_inr_per_window'])} from {', '.join(ra['from'])} to {', '.join(ra['to'])} nets about {ra['net_registrations_est']:+d} registrations. ASSUMPTION: {ra['assumption']}")
        return "\n".join(lines)
    if camp or any(w in ql for w in ("campaign", "channel", "compare", "cost per", "cac", "cpr", "show rate", "no-show", "conversion")):
        r = use("get_campaign_performance")
        rows = [c for c in r["campaigns"] if not camp or c["campaign_id"] == camp["campaign_id"]]
        lines = [f"Campaign performance as of {as_of} (external people; attribution = campaign on the registration):"]
        for c in rows:
            lines.append(f"- {c['campaign_name']}: spend {_inr(c['spend_inr'])}, {c['registered_external_people']} registered, {c['confirmed']} confirmed, "
                         f"{c['unique_external_visitors']} verified visitors, cost/registration {_inr(c['cost_per_registration'])}, cost/visitor {_inr(c['cost_per_visitor'])}, show rate {_pct(c['show_rate_confirmed'])}")
        return "\n".join(lines)
    if any(w in ql for w in ("how are we", "overview", "funnel", "summary", "status", "target", "goal", "budget", "spend", "forecast", "project", "on track", "attend", "visitor", "registr")):
        o = use("get_overview")
        x, v, f = o["metrics"], o["vs_target"], o["forecast"]
        lines = [f"As of {as_of} ({o['phase']}, target version: {o['target_version']}):",
                 f"- Anonymous events: {x['impressions']:,} impressions, {x['clicks']:,} clicks, {x['landing_page_sessions']:,} landing sessions, {x['registration_starts']:,} form starts (events, not people).",
                 f"- People: {x['identified_external_people']:,} identified, {x['registered_external_people']:,} registered, {x['confirmed']:,} confirmed, {x['unique_external_visitors']:,} verified visitors."]
        for k, label in (("identified_external_people", "Identified"), ("registered_external_people", "Registered"), ("unique_external_visitors", "Verified visitors"), ("spend_inr", "Spend vs budget")):
            lines.append(f"- {label}: {v[k]['actual']:,} of {v[k]['goal']:,} ({_pct(v[k]['pct_of_goal'])})" if v[k]["goal"] else f"- {label}: {v[k]['actual']:,} (no goal set)")
        lines.append(f"- {'Result' if f['basis']=='actual' else 'Forecast'}: {f['projected_visitors']:,} visitors vs goal {f['visitor_goal']}. {f['note']}")
        return "\n".join(lines)
    return ("I can't answer that in rule-based mode. Without an AI key I only handle: overall funnel/targets/budget/forecast, campaign comparisons, "
            "scale/fix/stop recommendations, task lists, and 'create a task to ...'. I won't guess at anything else.")
