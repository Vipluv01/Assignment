"""Analytics engine for the Growth Center (attendee growth).

Pure Python, no third-party imports. Everything the dashboard, the decision rules and the
AI copilot show is computed here from (source dataset + the team's saved changes), so the
three surfaces can never disagree.

Counting rules, taken from the dataset's own "Read me" sheet:
  * A selected date means END OF THAT DAY in IST. Nothing later may leak into the snapshot.
  * Rows repeating a stable ID (activity_id / history_id / event_id ...) are import retries:
    count once.
  * Registration status = the LATEST history version effective on or before the snapshot.
  * Targets are for EXTERNAL people. internal / staff / test identities are excluded from
    every headline number.
  * An actual visitor = a distinct external person with at least one check-in that is both
    result=admitted AND verification=verified. Denied / pending / unverified do not count.
  * impressions, clicks, sessions, registration_starts and reported_reach are anonymous EVENT
    counts. They are not people, and summed reach is not unique reach.
  * Campaign attribution = the campaign recorded on the registration (source relationship).
    Walk-ins have no campaign and are reported as unattributed.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import operator
import pathlib
from collections import defaultdict

DATA_PATH = pathlib.Path(__file__).resolve().parent / "data" / "attendee.json"

DEFAULT_SETTINGS = {
    "window_days": 14,            # trailing window used for pace and decision rules
    "assumed_show_rate": 0.75,    # ASSUMPTION used only before the event: confirmed -> attended
    "scale_cost_ratio": 0.80,     # cost <= 0.80x blended  -> SCALE
    "stop_cost_ratio": 1.50,      # cost >= 1.50x blended  -> STOP / restructure
    "fix_conversion_ratio": 0.75, # registrations per session < 0.75x blended -> FIX funnel
    "fix_show_ratio": 0.80,       # show rate < 0.80x blended -> FIX attendance
    "fix_cancel_ratio": 1.50,     # cancellation rate > 1.5x blended -> FIX retention
    "fix_optout_ratio": 2.00,     # opt-out rate > 2x blended -> FIX messaging pressure
    "min_sample_registrations": 20,
}

ID_COLS = {
    "daily": "activity_id",
    "people": "person_id",
    "interactions": "interaction_id",
    "registrations": "registration_id",
    "registration_history": "history_id",
    "checkins": "event_id",
    "campaigns": "campaign_id",
}
TIME_COLS = {
    "daily": "activity_date",
    "people": "first_seen_at",
    "interactions": "occurred_at",
    "registrations": "registered_at",
    "registration_history": "effective_at",
    "checkins": "occurred_at",
}

_BASE_CACHE: dict | None = None


def load_base() -> dict:
    """Source tables as lists of dicts, de-duplicated on their stable IDs."""
    global _BASE_CACHE
    if _BASE_CACHE is None:
        raw = json.loads(DATA_PATH.read_text())
        base, dup = {}, {}
        for name, t in raw.items():
            rows = [dict(zip(t["cols"], [int(v) if isinstance(v, float) and v.is_integer() else v for v in r])) for r in t["rows"]]
            key = ID_COLS.get(name)
            if key:
                seen, out = set(), []
                for r in rows:
                    if r[key] in seen:
                        continue
                    seen.add(r[key])
                    out.append(r)
                dup[name] = len(rows) - len(out)
                rows = out
            base[name] = rows
        for r in base["daily"]:
            r["activity_date"] = str(r["activity_date"])[:10]
        base["_duplicates_removed"] = dup
        _BASE_CACHE = base
    return _BASE_CACHE


def _end_of_day(day: str) -> str:
    return day[:10] + "T23:59:59"


def _d(day: str) -> dt.date:
    return dt.date.fromisoformat(day[:10])


def _ratio(a, b, nd=4):
    return round(a / b, nd) if b else None


def _num(v, default=0):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


class Model:
    """Source data merged with the team's saved changes (the 'overlay')."""

    def __init__(self, overlay: dict | None = None):
        ov = overlay or {}
        base = load_base()
        self.warnings: list[str] = []
        self.event = base["event"][0]
        self.event_start = self.event["event_starts_at"][:10]
        self.event_end = self.event["event_ends_at"][:10]
        self.history_start = self.event["history_start"][:10]
        self.history_end = self.event["history_end"][:10]
        self.duplicates_removed = base["_duplicates_removed"]
        self.settings = {**DEFAULT_SETTINGS, **{k: v for k, v in (ov.get("settings") or {}).items() if k in DEFAULT_SETTINGS and v not in (None, "")}}
        for k in self.settings:
            self.settings[k] = float(self.settings[k]) if k not in ("window_days", "min_sample_registrations") else int(float(self.settings[k]))

        # campaigns: source + team-created, with management fields layered on top
        self.campaigns = []
        edits = ov.get("campaign_edits") or {}
        for c in list(base["campaigns"]) + list(ov.get("new_campaigns") or []):
            c = dict(c)
            c.setdefault("source", "team" if c["campaign_id"].startswith("U") else "dataset")
            c.setdefault("status", "active")
            c.setdefault("budget_inr", None)
            c.setdefault("visitor_goal", None)
            c.setdefault("notes", "")
            c.update({k: v for k, v in (edits.get(c["campaign_id"]) or {}).items() if k in ("status", "budget_inr", "visitor_goal", "notes", "owner_name", "campaign_name", "planned_end_at", "planned_start_at")})
            self.campaigns.append(c)
        self.camp = {c["campaign_id"]: c for c in self.campaigns}

        def cname(cid):
            return self.camp[cid]["campaign_name"] if cid in self.camp else None

        self.targets = sorted(list(base["targets"]) + list(ov.get("targets") or []), key=lambda t: t["effective_at"])
        self.tasks = [dict(t) for t in (ov.get("tasks") or [])]

        self.daily = [dict(r) for r in base["daily"]]
        for r in ov.get("daily") or []:
            if r.get("campaign_id") not in self.camp:
                self.warnings.append(f"Ignored activity log {r.get('activity_id')}: unknown campaign {r.get('campaign_id')}")
                continue
            self.daily.append({
                "campaign_name": cname(r["campaign_id"]), "owner_name": self.camp[r["campaign_id"]].get("owner_name"),
                "activity_date": str(r["activity_date"])[:10],
                "impressions": _num(r.get("impressions")), "clicks": _num(r.get("clicks")),
                "reported_reach": _num(r.get("reported_reach")), "landing_page_sessions": _num(r.get("landing_page_sessions")),
                "registration_starts": _num(r.get("registration_starts")), "marketing_spend_inr": _num(r.get("marketing_spend_inr")),
                "platform": "team entry", "activity_id": r["activity_id"], "campaign_id": r["campaign_id"], "note": r.get("note", ""),
            })

        self.people = [dict(r) for r in base["people"]]
        self.interactions = base["interactions"]
        self.registrations = [dict(r) for r in base["registrations"]]
        self.history = [dict(r) for r in base["registration_history"]]
        self.checkins = [dict(r) for r in base["checkins"]]
        self._apply_outcomes(ov.get("outcomes") or [])

        self.person = {p["person_id"]: p for p in self.people}
        self.external = {p["person_id"] for p in self.people if p["person_type"] == "external"}
        self.reg_by_id = {r["registration_id"]: r for r in self.registrations}
        self.history.sort(key=lambda h: (h["effective_at"], h["history_id"]))

    # ---- team-entered outcomes become ordinary rows so every metric picks them up ----
    def _apply_outcomes(self, outcomes):
        for o in sorted(outcomes, key=lambda o: (str(o.get("date")), str(o.get("id")))):
            oid, day, cid = o["id"], str(o["date"])[:10], o.get("campaign_id") or None
            if cid and cid not in self.camp:
                self.warnings.append(f"Ignored outcome log {oid}: unknown campaign {cid}")
                continue
            cn = self.camp[cid]["campaign_name"] if cid else None
            own = self.camp[cid].get("owner_name") if cid else None
            n_leads, n_regs, n_chk = _num(o.get("new_leads")), _num(o.get("new_registrations")), _num(o.get("verified_checkins"))
            if (n_leads or n_regs) and not cid:
                self.warnings.append(f"Outcome log {oid}: leads/registrations need a campaign; ignored those counts")
                n_leads = n_regs = 0
            for i in range(n_leads + n_regs):
                pid = f"U{oid}-{i+1:04d}"
                self.people.append({"person_name": f"Team-logged person {pid}", "person_type": "external", "first_seen_at": f"{day}T09:00:00",
                                    "first_touch_source": "campaign", "first_campaign_name": cn, "owner_name": own, "person_id": pid, "first_campaign_id": cid})
                if i >= n_leads:
                    rid = f"UR{oid}-{i+1:04d}"
                    self.registrations.append({"person_name": f"Team-logged person {pid}", "campaign_name": cn, "owner_name": own,
                                               "registered_at": f"{day}T10:00:00", "registration_id": rid, "person_id": pid, "campaign_id": cid})
                    self.history.append({"person_name": f"Team-logged person {pid}", "campaign_name": cn, "effective_at": f"{day}T10:00:00",
                                         "status": "confirmed", "history_id": f"UH{oid}-{i+1:04d}", "registration_id": rid, "person_id": pid, "campaign_id": cid})
            if n_chk:
                if cid:
                    cutoff = f"{day}T12:00:00"
                    latest = {}
                    for h in sorted(self.history, key=lambda h: (h["effective_at"], h["history_id"])):
                        if h["effective_at"] <= cutoff:
                            latest[h["registration_id"]] = h
                    attended = {c["person_id"] for c in self.checkins if c["result"] == "admitted" and c["verification"] == "verified"}
                    pool = sorted(h["registration_id"] for h in latest.values() if h["campaign_id"] == cid and h["status"] == "confirmed" and h["person_id"] not in attended)
                    regmap = {r["registration_id"]: r for r in self.registrations}
                    if len(pool) < n_chk:
                        self.warnings.append(f"Outcome log {oid}: asked for {n_chk} check-ins on {cn} but only {len(pool)} confirmed registrants had not yet attended; logged {len(pool)}")
                    for i, rid in enumerate(pool[:n_chk]):
                        r = regmap[rid]
                        self.checkins.append({"person_name": r["person_name"], "campaign_name": cn, "owner_name": own, "occurred_at": cutoff, "result": "admitted",
                                              "verification": "verified", "source": "manual", "event_id": f"UC{oid}-{i+1:04d}", "person_id": r["person_id"],
                                              "registration_id": rid, "campaign_id": cid})
                else:  # unattributed walk-ins
                    for i in range(n_chk):
                        pid = f"UW{oid}-{i+1:04d}"
                        self.people.append({"person_name": f"Team-logged walk-in {pid}", "person_type": "external", "first_seen_at": f"{day}T12:00:00",
                                            "first_touch_source": "walk_in", "first_campaign_name": None, "owner_name": None, "person_id": pid, "first_campaign_id": None})
                        self.checkins.append({"person_name": f"Team-logged walk-in {pid}", "campaign_name": None, "owner_name": None, "occurred_at": f"{day}T12:00:00",
                                              "result": "admitted", "verification": "verified", "source": "manual", "event_id": f"UC{oid}-{i+1:04d}", "person_id": pid,
                                              "registration_id": None, "campaign_id": None})

    # ------------------------------------------------------------------ helpers
    def clamp(self, as_of: str | None) -> str:
        return (as_of or self.default_as_of())[:10]

    def default_as_of(self) -> str:
        last = max([self.history_end] + [r["activity_date"] for r in self.daily] + [r["registered_at"][:10] for r in self.registrations])
        return last

    def target_at(self, as_of: str) -> dict | None:
        cut, cur = _end_of_day(as_of), None
        for t in self.targets:
            if t["effective_at"] <= cut:
                cur = t
        return cur

    def latest_status(self, as_of: str) -> dict:
        """registration_id -> latest history row effective at or before end of as_of."""
        cut, out = _end_of_day(as_of), {}
        for h in self.history:  # sorted by effective_at
            if h["effective_at"] <= cut:
                out[h["registration_id"]] = h
        return out

    def verified_visitors(self, as_of: str, since: str | None = None) -> dict:
        """person_id -> first verified admitted check-in row (external people only)."""
        cut, lo, out = _end_of_day(as_of), (since + "T00:00:00" if since else ""), {}
        for c in self.checkins:
            if c["occurred_at"] <= cut and c["occurred_at"] >= lo and c["result"] == "admitted" and c["verification"] == "verified" and c["person_id"] in self.external:
                if c["person_id"] not in out or c["occurred_at"] < out[c["person_id"]]["occurred_at"]:
                    out[c["person_id"]] = c
        return out

    # ------------------------------------------------------------------ core metrics
    def metrics(self, as_of: str | None = None, since: str | None = None, campaign_id: str | None = "__all__") -> dict:
        """Funnel metrics as of end of `as_of`. `since` (inclusive day) restricts the
        flow metrics to a window. campaign_id="__all__" = whole event; None = unattributed."""
        as_of = self.clamp(as_of)
        cut, lo, lo_day = _end_of_day(as_of), (since[:10] + "T00:00:00" if since else ""), (since[:10] if since else "")
        allc = campaign_id == "__all__"

        def camp_ok(v):
            return allc or v == campaign_id

        m = dict(impressions=0, clicks=0, reported_reach_sum=0, landing_page_sessions=0, registration_starts=0, spend_inr=0)
        for r in self.daily:
            if lo_day <= r["activity_date"] <= as_of and camp_ok(r["campaign_id"]):
                m["impressions"] += r["impressions"] or 0
                m["clicks"] += r["clicks"] or 0
                m["reported_reach_sum"] += r["reported_reach"] or 0
                m["landing_page_sessions"] += r["landing_page_sessions"] or 0
                m["registration_starts"] += r["registration_starts"] or 0
                m["spend_inr"] += r["marketing_spend_inr"] or 0

        ident = {p["person_id"] for p in self.people if p["person_id"] in self.external and lo <= p["first_seen_at"] <= cut and camp_ok(p.get("first_campaign_id"))}
        regs = [r for r in self.registrations if r["person_id"] in self.external and lo <= r["registered_at"] <= cut and camp_ok(r["campaign_id"])]
        reg_people = {r["person_id"] for r in regs}
        latest = self.latest_status(as_of)
        status = defaultdict(int)
        confirmed_people = set()
        for r in regs:
            h = latest.get(r["registration_id"])
            s = h["status"] if h else "unknown"
            status[s] += 1
            if s == "confirmed":
                confirmed_people.add(r["person_id"])
        vis = self.verified_visitors(as_of, since)
        person_campaign = {r["person_id"]: r["campaign_id"] for r in self.registrations}
        if allc:
            visitors = set(vis)
        else:
            visitors = {p for p in vis if person_campaign.get(p) == campaign_id} if campaign_id else {p for p in vis if p not in person_campaign}
        registered_visitors = {p for p in visitors if p in person_campaign}
        optout = {i["person_id"] for i in self.interactions if i["event_type"] == "opted_out" and lo <= i["occurred_at"] <= cut and camp_ok(i["campaign_id"]) and i["person_id"] in self.external}

        n_reg, n_vis = len(reg_people), len(visitors)
        attended_confirmed = len(confirmed_people & set(vis))
        m.update(
            identified_external_people=len(ident),
            registered_external_people=n_reg,
            confirmed=status.get("confirmed", 0), interested=status.get("interested", 0),
            waitlisted=status.get("waitlisted", 0), cancelled=status.get("cancelled", 0),
            unique_external_visitors=n_vis,
            visitors_with_registration=len(registered_visitors),
            walk_in_visitors=n_vis - len(registered_visitors),
            opted_out_people=len(optout),
            ctr=_ratio(m["clicks"], m["impressions"]),
            click_to_session=_ratio(m["landing_page_sessions"], m["clicks"]),
            session_to_start=_ratio(m["registration_starts"], m["landing_page_sessions"]),
            registrations_per_session=_ratio(n_reg, m["landing_page_sessions"]),
            identified_to_registered=_ratio(len(reg_people & ident) if not since else n_reg, len(ident)),
            confirm_rate=_ratio(status.get("confirmed", 0), n_reg),
            cancel_rate=_ratio(status.get("cancelled", 0), n_reg),
            optout_rate=_ratio(len(optout), len(ident)),
            show_rate_confirmed=_ratio(attended_confirmed, status.get("confirmed", 0)) if as_of >= self.event_start else None,
            cost_per_registration=_ratio(m["spend_inr"], n_reg, 2),
            cost_per_visitor=(_ratio(m["spend_inr"], n_vis, 2) if as_of >= self.event_start else None),
        )
        return m

    def overview(self, as_of: str | None = None) -> dict:
        as_of = self.clamp(as_of)
        m = self.metrics(as_of)
        t = self.target_at(as_of) or {}
        goals = {
            "identified_external_people": t.get("identified_external_people_goal"),
            "registered_external_people": t.get("registration_goal"),
            "unique_external_visitors": t.get("unique_external_visitors_goal"),
            "spend_inr": t.get("marketing_budget_inr"),
        }
        vs = {}
        for k, g in goals.items():
            vs[k] = {"actual": m[k], "goal": g, "pct_of_goal": _ratio(m[k], g), "gap": (g - m[k]) if g is not None else None}
        return {
            "as_of": as_of, "event_start": self.event_start, "event_end": self.event_end,
            "days_to_event": (_d(self.event_start) - _d(as_of)).days,
            "phase": "pre-event" if as_of < self.event_start else ("event live" if as_of <= self.event_end else "post-event"),
            "target_version": t.get("target_version"), "metrics": m, "vs_target": vs,
            "budget_remaining_inr": (goals["spend_inr"] - m["spend_inr"]) if goals["spend_inr"] is not None else None,
            "forecast": self.forecast(as_of, m, t),
            "definitions": DEFINITIONS, "warnings": self.warnings,
        }

    def forecast(self, as_of: str, m: dict | None = None, t: dict | None = None) -> dict:
        as_of = self.clamp(as_of)
        m = m or self.metrics(as_of)
        t = t if t is not None else (self.target_at(as_of) or {})
        w = self.settings["window_days"]
        goal_v, goal_r, budget = t.get("unique_external_visitors_goal"), t.get("registration_goal"), t.get("marketing_budget_inr")
        if as_of >= self.event_end:
            return {"basis": "actual", "note": "Event is over: these are actuals, not a projection.",
                    "projected_registrations": m["registered_external_people"], "projected_visitors": m["unique_external_visitors"],
                    "projected_spend_inr": m["spend_inr"], "visitor_goal": goal_v,
                    "visitor_gap_vs_goal": (m["unique_external_visitors"] - goal_v) if goal_v else None}
        eve = _d(self.event_start) - dt.timedelta(days=1)
        days_left = max((eve - _d(as_of)).days, 0)
        since = (_d(as_of) - dt.timedelta(days=w - 1)).isoformat()
        win = self.metrics(as_of, since)
        elapsed = max(min(w, (_d(as_of) - _d(self.history_start)).days + 1), 1)
        reg_pace, spend_pace = win["registered_external_people"] / elapsed, win["spend_inr"] / elapsed
        proj_regs = m["registered_external_people"] + reg_pace * days_left
        confirm = m["confirm_rate"] if m["confirm_rate"] is not None else 0.85
        show = self.settings["assumed_show_rate"]
        proj_vis = proj_regs * confirm * show
        need = None
        if goal_v and days_left and confirm and show:
            need = max((goal_v / (confirm * show) - m["registered_external_people"]) / days_left, 0)
        return {
            "basis": "projection",
            "note": f"Linear projection: last {elapsed}-day registration pace held to event eve; confirm rate held at today's {confirm:.0%}; "
                    f"show rate {show:.0%} is an ASSUMPTION (no attendance exists before the event). Walk-ins excluded.",
            "days_left_to_event_eve": days_left,
            "registrations_per_day_recent": round(reg_pace, 1), "spend_per_day_recent_inr": round(spend_pace),
            "projected_registrations": round(proj_regs), "projected_confirmed": round(proj_regs * confirm),
            "projected_visitors": round(proj_vis), "visitor_goal": goal_v, "registration_goal": goal_r,
            "visitor_gap_vs_goal": round(proj_vis - goal_v) if goal_v else None,
            "registrations_per_day_needed_for_visitor_goal": round(need, 1) if need is not None else None,
            "projected_spend_inr": round(m["spend_inr"] + spend_pace * days_left), "budget_inr": budget,
            "projected_budget_overrun_inr": round(m["spend_inr"] + spend_pace * days_left - budget) if budget else None,
        }

    def campaign_table(self, as_of: str | None = None, since: str | None = None) -> list[dict]:
        as_of = self.clamp(as_of)
        rows = []
        for c in self.campaigns:
            m = self.metrics(as_of, since, c["campaign_id"])
            rows.append({"campaign_id": c["campaign_id"], "campaign_name": c["campaign_name"], "channel": c.get("channel"), "owner_name": c.get("owner_name"),
                         "status": c.get("status"), "budget_inr": c.get("budget_inr"), "visitor_goal": c.get("visitor_goal"), **m})
        u = self.metrics(as_of, since, None)
        if u["unique_external_visitors"] or u["identified_external_people"]:
            rows.append({"campaign_id": None, "campaign_name": "Unattributed (walk-ins)", "channel": None, "owner_name": None, "status": None, "budget_inr": None, "visitor_goal": None, **u})
        return rows

    def time_series(self, as_of: str | None = None, campaign_id: str | None = "__all__") -> list[dict]:
        """One row per day from history start to as_of with daily and cumulative values."""
        as_of = self.clamp(as_of)
        allc = campaign_id == "__all__"
        ok = lambda v: allc or v == campaign_id
        day = defaultdict(lambda: defaultdict(int))
        for r in self.daily:
            if r["activity_date"] <= as_of and ok(r["campaign_id"]):
                d = day[r["activity_date"]]
                d["spend_inr"] += r["marketing_spend_inr"] or 0
                d["sessions"] += r["landing_page_sessions"] or 0
                d["clicks"] += r["clicks"] or 0
                d["impressions"] += r["impressions"] or 0
        for p in self.people:
            if p["person_id"] in self.external and p["first_seen_at"][:10] <= as_of and ok(p.get("first_campaign_id")):
                day[p["first_seen_at"][:10]]["identified"] += 1
        for r in self.registrations:
            if r["person_id"] in self.external and r["registered_at"][:10] <= as_of and ok(r["campaign_id"]):
                day[r["registered_at"][:10]]["registrations"] += 1
        pc = {r["person_id"]: r["campaign_id"] for r in self.registrations}
        for pid, c in self.verified_visitors(as_of).items():
            if ok(pc.get(pid)):
                day[c["occurred_at"][:10]]["visitors"] += 1
        out, cum = [], defaultdict(int)
        d, end = _d(self.history_start), _d(as_of)
        while d <= end:
            k = d.isoformat()
            row = {"date": k}
            t = self.target_at(k) or {}
            for f in ("identified", "registrations", "visitors", "spend_inr", "sessions", "clicks", "impressions"):
                v = day[k][f] if k in day else 0
                cum[f] += v
                row[f] = v
                row["cum_" + f] = cum[f]
            row["registration_goal"] = t.get("registration_goal")
            row["visitor_goal"] = t.get("unique_external_visitors_goal")
            row["budget_inr"] = t.get("marketing_budget_inr")
            out.append(row)
            d += dt.timedelta(days=1)
        return out

    # ------------------------------------------------------------------ decisions
    def decisions(self, as_of: str | None = None) -> dict:
        """Scale / fix / stop verdict per campaign from explicit, editable thresholds."""
        as_of = self.clamp(as_of)
        s = self.settings
        post = as_of >= self.event_start
        if post:
            since, basis = None, "whole campaign (attendance is known)"
        else:
            since = max(self.history_start, (_d(as_of) - dt.timedelta(days=s["window_days"] - 1)).isoformat())
            basis = f"trailing {s['window_days']} days ({since} to {as_of})"
        blended = self.metrics(as_of, since)
        cum_all = self.metrics(as_of)
        cost_key = "cost_per_visitor" if post else "cost_per_registration"
        cost_label = "cost per verified visitor" if post else "cost per registration"
        out = []
        for c in self.campaigns:
            cid = c["campaign_id"]
            w, cum = self.metrics(as_of, since, cid), self.metrics(as_of, None, cid)
            ev, flags, verdict = [], [], "HOLD"
            volume = w["unique_external_visitors"] if post else w["registered_external_people"]
            cost, bcost = w[cost_key], blended[cost_key]
            if w["registered_external_people"] < s["min_sample_registrations"] and w["spend_inr"] < 5000:
                verdict = "INSUFFICIENT DATA"
                ev.append(f"Only {w['registered_external_people']} registrations and ₹{w['spend_inr']:,} spend in the window: too little to judge.")
            else:
                if cost is not None and bcost:
                    r = cost / bcost
                    ev.append(f"{cost_label}: ₹{cost:,.0f} vs blended ₹{bcost:,.0f} ({r:.2f}x)")
                    if r >= s["stop_cost_ratio"]:
                        verdict = "STOP"
                    elif r <= s["scale_cost_ratio"]:
                        verdict = "SCALE"
                elif w["spend_inr"] > 0 and not volume:
                    verdict = "STOP"
                    ev.append(f"₹{w['spend_inr']:,} spent in the window with no {'verified visitors' if post else 'registrations'}.")

                def check(key, label, ratio, worse_low, tag):
                    a, b = cum[key], cum_all[key]
                    if a is None or not b:
                        return
                    bad = a < ratio * b if worse_low else a > ratio * b
                    if bad:
                        flags.append(tag)
                        ev.append(f"{label}: {a:.1%} vs blended {b:.1%}")

                check("registrations_per_session", "registrations per landing session", s["fix_conversion_ratio"], True, "landing-to-registration conversion")
                check("cancel_rate", "cancellation rate", s["fix_cancel_ratio"], False, "cancellations")
                check("optout_rate", "opt-out rate", s["fix_optout_ratio"], False, "opt-outs / contact pressure")
                if post:
                    check("show_rate_confirmed", "show rate (confirmed who attended)", s["fix_show_ratio"], True, "no-shows")
                if flags and verdict in ("HOLD", "SCALE"):
                    verdict = "FIX" if verdict == "HOLD" else "SCALE + FIX"
            action = {
                "SCALE": "Move budget and owner time here first.",
                "SCALE + FIX": f"Efficient, but fix {', '.join(flags)} before adding budget.",
                "FIX": f"Keep budget flat and fix {', '.join(flags)}.",
                "STOP": "Stop adding budget; restructure or reallocate." + (f" Also weak on {', '.join(flags)}." if flags else ""),
                "HOLD": "Performing near the blended average: keep running, no change.",
                "INSUFFICIENT DATA": "Keep the test running until the minimum sample is reached.",
            }[verdict]
            out.append({"campaign_id": cid, "campaign_name": c["campaign_name"], "owner_name": c.get("owner_name"), "status": c.get("status"),
                        "verdict": verdict, "action": action, "issues": flags, "evidence": ev,
                        "window": {"spend_inr": w["spend_inr"], "registrations": w["registered_external_people"], "visitors": w["unique_external_visitors"],
                                   "cost_per_registration": w["cost_per_registration"], "cost_per_visitor": w["cost_per_visitor"]},
                        "cumulative": {k: cum[k] for k in ("spend_inr", "registered_external_people", "confirmed", "unique_external_visitors", "cost_per_registration",
                                                             "cost_per_visitor", "registrations_per_session", "cancel_rate", "optout_rate", "show_rate_confirmed")}})
        order = {"STOP": 0, "FIX": 1, "SCALE + FIX": 2, "SCALE": 3, "HOLD": 4, "INSUFFICIENT DATA": 5}
        out.sort(key=lambda d: (order[d["verdict"]], -(d["window"]["spend_inr"] or 0)))

        # budget reallocation sketch
        t = self.target_at(as_of) or {}
        budget = t.get("marketing_budget_inr")
        remaining = budget - cum_all["spend_inr"] if budget is not None else None
        realloc = None
        if not post:
            stop = [d for d in out if d["verdict"] == "STOP"]
            scale = [d for d in out if d["verdict"].startswith("SCALE") and d["window"]["cost_per_registration"]]
            freed = sum(d["window"]["spend_inr"] for d in stop)
            if stop and scale and freed > 0:
                lost = sum(d["window"]["registrations"] for d in stop)
                avg_cpr = sum(d["window"]["spend_inr"] for d in scale) / max(sum(d["window"]["registrations"] for d in scale), 1)
                gained = freed / avg_cpr if avg_cpr else 0
                realloc = {"from": [d["campaign_name"] for d in stop], "to": [d["campaign_name"] for d in scale], "amount_inr_per_window": freed,
                           "registrations_lost": lost, "registrations_gained_est": round(gained), "net_registrations_est": round(gained - lost),
                           "assumption": "Assumes the SCALE campaigns keep their recent cost per registration at higher spend (marginal cost usually rises) "
                                         "and ignores differences in show rate, which is unknown before the event."}
        return {"as_of": as_of, "basis": basis, "cost_metric": cost_label, "blended_cost": blended[cost_key], "thresholds": s,
                "budget_inr": budget, "budget_remaining_inr": remaining, "reallocation": realloc, "campaigns": out}

    # ------------------------------------------------------------------ generic query (used by the copilot)
    def table(self, name: str, as_of: str) -> list[dict]:
        cut = _end_of_day(as_of)
        if name == "campaigns":
            return self.campaigns
        if name == "targets":
            return self.targets
        if name == "tasks":
            return [{**t, "overdue": bool(t.get("due_date") and t["due_date"] < as_of and t.get("status") != "done")} for t in self.tasks]
        if name == "daily":
            return [r for r in self.daily if r["activity_date"] <= as_of]
        if name == "people":
            return [p for p in self.people if p["first_seen_at"] <= cut]
        if name == "interactions":
            return [{**i, "person_type": self.person.get(i["person_id"], {}).get("person_type")} for i in self.interactions if i["occurred_at"] <= cut]
        if name == "registration_history":
            return [h for h in self.history if h["effective_at"] <= cut]
        if name == "checkins":
            return [{**c, "person_type": self.person.get(c["person_id"], {}).get("person_type")} for c in self.checkins if c["occurred_at"] <= cut]
        if name == "registrations":
            latest = self.latest_status(as_of)
            vis = self.verified_visitors(as_of)
            out = []
            for r in self.registrations:
                if r["registered_at"] <= cut:
                    h = latest.get(r["registration_id"])
                    out.append({**r, "person_type": self.person.get(r["person_id"], {}).get("person_type"), "status": h["status"] if h else None,
                                "status_effective_at": h["effective_at"] if h else None, "attended_verified": r["person_id"] in vis})
            return out
        raise ValueError(f"Unknown table '{name}'. Available: {', '.join(TABLE_DOCS)}")

    def query(self, spec: dict, default_as_of: str | None = None) -> dict:
        as_of = self.clamp(spec.get("as_of") or default_as_of)
        rows = self.table(spec.get("table", ""), as_of)
        fields = sorted({k for r in rows[:50] for k in r}) if rows else []

        def derive(row, f):
            if "(" in f and f.endswith(")"):
                fn, inner = f[:-1].split("(", 1)
                v = row.get(inner)
                if inner not in row:
                    raise KeyError(inner)
                if v is None:
                    return None
                v = str(v)
                if fn == "date":
                    return v[:10]
                if fn == "month":
                    return v[:7]
                if fn == "week":
                    d = _d(v)
                    return (d - dt.timedelta(days=d.weekday())).isoformat()
                if fn == "hour":
                    return v[11:13] if len(v) > 12 else None
                if fn == "weekday":
                    return _d(v).strftime("%A")
                raise ValueError(f"Unknown function '{fn}'. Use date(), week(), month(), hour(), weekday().")
            if f not in row:
                raise KeyError(f)
            return row[f]

        try:
            for flt in spec.get("filters") or []:
                f, op, val = flt["field"], flt.get("op", "eq"), flt.get("value")
                def keep(r, f=f, op=op, val=val):
                    v = derive(r, f)
                    if isinstance(val, str) and isinstance(v, bool):
                        val = val.lower() == "true"
                    elif isinstance(val, str) and isinstance(v, (int, float)):
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                    if op == "is_null":
                        return v is None or v == ""
                    if op == "not_null":
                        return v is not None and v != ""
                    if op == "in":
                        return v in (val or [])
                    if op == "not_in":
                        return v not in (val or [])
                    if op == "contains":
                        return v is not None and str(val).lower() in str(v).lower()
                    if op == "eq":
                        return v == val
                    if op == "ne":
                        return v != val
                    if v is None:
                        return False
                    a, b = (v, val) if isinstance(v, (int, float)) and isinstance(val, (int, float)) else (str(v), str(val))
                    if op in ("lte", "lt") and isinstance(a, str) and len(b) == 10 and len(a) > 10:
                        b = b + ("T23:59:59" if op == "lte" else "")
                    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
                if op not in ("eq", "ne", "in", "not_in", "contains", "gt", "gte", "lt", "lte", "is_null", "not_null"):
                    raise ValueError(f"Unknown filter op '{op}'")
                rows = [r for r in rows if keep(r)]
            matched = len(rows)
            group_by, aggs = spec.get("group_by") or [], spec.get("aggregates") or []
            if group_by or aggs:
                groups = defaultdict(list)
                for r in rows:
                    groups[tuple(derive(r, g) for g in group_by)].append(r)
                if not group_by and not groups:
                    groups[()] = []
                res = []
                for key, grp in groups.items():
                    o = dict(zip(group_by, key))
                    for a in aggs or [{"op": "count"}]:
                        op, f = a.get("op", "count"), a.get("field")
                        name = a.get("as") or (f"{op}_{f}" if f else op)
                        if op == "count":
                            o[name] = len(grp)
                            continue
                        vals = [derive(r, f) for r in grp]
                        vals = [v for v in vals if v is not None and v != ""]
                        if op == "count_distinct":
                            o[name] = len(set(vals))
                        elif op in ("sum", "avg"):
                            nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
                            o[name] = (sum(nums) if op == "sum" else (round(sum(nums) / len(nums), 4) if nums else None))
                        elif op in ("min", "max"):
                            o[name] = (min(vals) if op == "min" else max(vals)) if vals else None
                        else:
                            raise ValueError(f"Unknown aggregate op '{op}'. Use count, count_distinct, sum, avg, min, max.")
                    res.append(o)
                rows = res
            elif spec.get("select"):
                rows = [{f: derive(r, f) for f in spec["select"]} for r in rows]
            for ob in reversed(spec.get("order_by") or []):
                f, desc = (ob.get("field"), ob.get("dir", "asc") == "desc") if isinstance(ob, dict) else (ob, False)
                rows = sorted(rows, key=lambda r: (r.get(f) is None, r.get(f) if r.get(f) is not None else 0), reverse=desc)
        except KeyError as e:
            return {"error": f"Field {e} does not exist in table '{spec.get('table')}'. Available fields: {', '.join(fields)}. "
                             "If the concept is not in this list, the data does not contain it."}
        except (ValueError, TypeError) as e:
            return {"error": str(e)}
        limit = min(int(spec.get("limit") or 50), 200)
        return {"table": spec.get("table"), "as_of": as_of, "rows_matched": matched, "rows_returned": min(len(rows), limit),
                "truncated": len(rows) > limit, "rows": rows[:limit]}


# ---------------------------------------------------------------------- safe calculator
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs}


def calculate(expression: str):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("Only numbers, + - * / ** % // and round/min/max/abs are allowed")
    return ev(ast.parse(expression.replace(",", "").replace("₹", "").replace("%", "/100"), mode="eval"))


DEFINITIONS = {
    "identified_external_people": "Distinct external people first seen on or before the date (includes event-day walk-ins).",
    "registered_external_people": "Distinct external people with a registration created on or before the date.",
    "confirmed": "External registrations whose latest status on the date is 'confirmed'.",
    "unique_external_visitors": "Distinct external people with at least one admitted AND verified check-in. This is 'actual attendance'.",
    "spend_inr": "Net posted marketing spend (debits less credits) in whole INR. Negative rows are vendor credits.",
    "impressions/clicks/sessions/registration_starts": "Anonymous event counts, not people. Useful for rates, not for head-counts.",
    "reported_reach_sum": "Sum of daily platform-reported reach. NOT unique reach: the same person is counted on every day they are reached.",
    "show_rate_confirmed": "Confirmed registrants with a verified admission / confirmed registrants. Only meaningful from event day.",
    "cost_per_registration": "Spend / registered external people (campaign attribution = campaign recorded on the registration).",
    "cost_per_visitor": "Spend / unique external visitors. For a campaign, visitors are those whose registration is attributed to it; walk-ins are unattributed.",
    "registrations_per_session": "Registered external people / anonymous landing-page sessions. Mixed units: a comparison index, not a true person-level conversion.",
}

TABLE_DOCS = {
    "campaigns": "campaign_id, campaign_name, channel, target_audience, objective, owner_name, planned_start_at, planned_end_at, status (active|paused|scaled|stopped|planned), budget_inr, visitor_goal, notes, source (dataset|team)",
    "targets": "effective_at, identified_external_people_goal, registration_goal, unique_external_visitors_goal, marketing_budget_inr, target_version (a version applies from effective_at until the next one)",
    "daily": "activity_id, campaign_id, campaign_name, activity_date, impressions, clicks, reported_reach, landing_page_sessions, registration_starts, marketing_spend_inr, platform  [anonymous event counts per campaign per day]",
    "people": "person_id, person_name, person_type (external|internal|staff|test), first_seen_at, first_touch_source (campaign|walk_in|internal_registration|event_access), first_campaign_id, first_campaign_name, owner_name",
    "interactions": "interaction_id, person_id, person_type, campaign_id, campaign_name, occurred_at, event_type (page_visit|brochure_download|registration_start|event_question_submitted|nurture_email_sent|nurture_email_opened|nurture_email_clicked|opted_out)",
    "registrations": "registration_id, person_id, person_name, person_type, campaign_id, campaign_name, registered_at, status (latest as of the date: interested|confirmed|cancelled|waitlisted), status_effective_at, attended_verified (bool)",
    "registration_history": "history_id, registration_id, person_id, campaign_id, campaign_name, effective_at, status  [every status version; do not count versions as people]",
    "checkins": "event_id, person_id, person_type, registration_id, campaign_id (null = unattributed walk-in), occurred_at, result (admitted|denied|pending), verification (verified|unverified), source (scanner|manual)",
    "tasks": "task_id, title, description, owner_name, due_date, status (todo|in_progress|blocked|done), priority (high|medium|low), campaign_id, source (manual|copilot|decision rule), created_at, evidence, overdue (bool, relative to the as-of date)",
}
