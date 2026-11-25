"""Quantitative model behind the three strategy slides (Challenge A, attendee growth).

Run:  python3 scripts/strategy_model.py
Everything marked FACT is computed from the provided Attendee Dataset by growth/engine.py.
Everything marked ASSUMPTION is a planning choice and is listed in the README.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from growth.engine import Model

m = Model()
FINAL = "2025-04-20"
tot = m.metrics(FINAL)
camp = {r["campaign_name"]: r for r in m.campaign_table(FINAL)}

# FACT: 2025 benchmark per channel
BENCH = {}
for name, r in camp.items():
    if r["campaign_id"]:
        BENCH[name] = dict(spend=r["spend_inr"], reg=r["registered_external_people"], vis=r["unique_external_visitors"],
                           cpv=r["spend_inr"] / r["unique_external_visitors"], show=r["unique_external_visitors"] / r["registered_external_people"])
WALKIN_RATIO = tot["walk_in_visitors"] / tot["visitors_with_registration"]          # FACT 125 / 1,925
CONFIRM = tot["confirmed"] / tot["registered_external_people"]                      # FACT 2,500 / 2,800
REG_PER_SESSION = tot["registered_external_people"] / tot["landing_page_sessions"]  # FACT (index: people / anonymous sessions)
SESSION_PER_CLICK = tot["landing_page_sessions"] / tot["clicks"]
CTR = tot["clicks"] / tot["impressions"]

BUDGET = 600_000  # ASSUMPTION: 2x the 2025 approved budget of Rs 3.0 lakh
# ASSUMPTION: plan spend per channel and how much cost per visitor worsens (or improves) versus 2025 at that scale.
#            channel                 spend    base-factor stretch-factor  rationale
PLAN = [("College Partnerships",   120_000, 1.40, 1.15, "3.9x spend; group bookings via clubs"),
        ("Campus Ambassadors",     140_000, 1.30, 1.10, "3.3x spend; paid per verified check-in"),
        ("Student Referrals",       80_000, 1.50, 1.20, "4.2x spend; rewards redeemed at the gate"),
        ("Community Groups",        50_000, 1.30, 1.15, "3.1x spend"),
        ("Organic Search",          30_000, 1.30, 1.15, "2.1x spend; content + listings"),
        ("Paid Social",             80_000, 0.85, 0.75, "cut 14%; retargeting warm visitors only"),
        ("Creator Partners",        50_000, 0.80, 0.70, "cut 15%; micro-creators on performance pay")]
SHOWUP_SPEND, CONTINGENCY = 30_000, 20_000
# ASSUMPTION: share of registrants who attend. 2025 blended FACT = 68.75%; the plan's channel mix alone gives ~74%
# (peer channels show up more); the show-up programme (idea 3) is assumed to add the rest. Best 2025 channel = 85.6%.
REG_TO_ATTEND = {"base": 0.78, "stretch": 0.82}
WALKIN = {"base": WALKIN_RATIO, "stretch": 0.10}  # stretch ASSUMPTION: day-2 "bring a friend" gate offer lifts walk-ins to 10%


def scenario(kind):
    rows, vis, regs = [], 0, 0
    for name, spend, fb, fs, why in PLAN:
        b = BENCH[name]
        cpv = b["cpv"] * (fb if kind == "base" else fs)
        v = spend / cpv
        rows.append(dict(channel=name, spend=spend, cpv_2025=b["cpv"], cpv_plan=cpv, visitors=v, registrations=v / b["show"], why=why))
        vis += v
        regs += v / b["show"]
    lifted = regs * REG_TO_ATTEND[kind]
    walk = lifted * WALKIN[kind]
    total = lifted + walk
    confirmed = regs * CONFIRM
    sessions = regs / REG_PER_SESSION
    clicks = sessions / SESSION_PER_CLICK
    return dict(kind=kind, rows=rows, channel_visitors=vis, showup_gain=lifted - vis, registered_visitors=lifted, walkins=walk, total=total,
                registrations=regs, confirmed=confirmed, sessions=sessions, clicks=clicks, impressions=clicks / CTR,
                reg_to_attend=lifted / regs, confirmed_to_attend=lifted / confirmed, spend=sum(r["spend"] for r in rows) + SHOWUP_SPEND + CONTINGENCY,
                cost_per_attendee=BUDGET / total)


BASE, STRETCH = scenario("base"), scenario("stretch")
BOTH_DAYS = (1430 + 1345 - tot["unique_external_visitors"]) / tot["unique_external_visitors"]  # FACT: share of 2025 visitors seen on both days


def peak_day(total):
    return total * (1 + BOTH_DAYS) / 2


if __name__ == "__main__":
    print(f"2025 FACTS: spend {tot['spend_inr']:,}  registered {tot['registered_external_people']:,}  confirmed {tot['confirmed']:,}  visitors {tot['unique_external_visitors']:,} "
          f"(walk-ins {tot['walk_in_visitors']})  cost/visitor {tot['spend_inr']/tot['unique_external_visitors']:.0f}  CTR {CTR:.2%}  reg/session {REG_PER_SESSION:.1%}  both-days {BOTH_DAYS:.0%}")
    for n, b in BENCH.items():
        print(f"  {n:22s} spend {b['spend']:>7,}  reg {b['reg']:>4}  visitors {b['vis']:>4}  cost/visitor {b['cpv']:6.1f}  reg->attend {b['show']:.1%}")
    for s in (BASE, STRETCH):
        print(f"\n{s['kind'].upper()}  total attendees {s['total']:,.0f}  (channels {s['channel_visitors']:,.0f} + show-up programme {s['showup_gain']:,.0f} + walk-ins {s['walkins']:,.0f})  spend {s['spend']:,}")
        print(f"  funnel: impressions {s['impressions']:,.0f} -> clicks {s['clicks']:,.0f} -> sessions {s['sessions']:,.0f} -> registrations {s['registrations']:,.0f} -> confirmed {s['confirmed']:,.0f} -> attended {s['registered_visitors']:,.0f} (+{s['walkins']:,.0f} walk-ins)")
        print(f"  registered->attended {s['reg_to_attend']:.1%}  confirmed->attended {s['confirmed_to_attend']:.1%}  cost/attendee {s['cost_per_attendee']:.0f}  peak-day attendance {peak_day(s['total']):,.0f}")
        for r in s["rows"]:
            print(f"    {r['channel']:22s} spend {r['spend']:>7,}  cost/visitor {r['cpv_2025']:6.1f} -> {r['cpv_plan']:6.1f}  visitors {r['visitors']:6.0f}  registrations {r['registrations']:6.0f}")


# ---------------------------------------------------------------- the five ideas and their ranking
# score = base-case attendees added per Rs 1,000 x confidence x speed
#   confidence (ASSUMPTION, 0-1): how directly 2025 data supports the idea
#   speed (ASSUMPTION): 1.0 if it can be proven or killed within 2 weeks, 0.8 if within 4, 0.6 if only near the event
def _idea(key, name, attendees, spend, confidence, speed):
    return dict(key=key, name=name, attendees=attendees, spend=spend, confidence=confidence, speed=speed,
                per_1000=attendees / spend * 1000, score=attendees / spend * 1000 * confidence * speed)


_b = {r["channel"]: r for r in BASE["rows"]}
IDEAS = sorted([
    _idea("squad", "Squad Pass through college clubs", _b["College Partnerships"]["visitors"], _b["College Partnerships"]["spend"], 0.85, 1.0),
    _idea("referral", "Referral rewards redeemed at the gate", _b["Student Referrals"]["visitors"], _b["Student Referrals"]["spend"], 0.85, 1.0),
    _idea("showup", "Show-up engine", BASE["showup_gain"], SHOWUP_SPEND, 0.70, 0.6),
    _idea("ambassador", "Campus ambassadors paid per verified check-in", _b["Campus Ambassadors"]["visitors"], _b["Campus Ambassadors"]["spend"], 0.85, 1.0),
    _idea("retarget", "Paid social and creators, rebuilt as retargeting", _b["Paid Social"]["visitors"] + _b["Creator Partners"]["visitors"],
          _b["Paid Social"]["spend"] + _b["Creator Partners"]["spend"], 0.50, 1.0),
], key=lambda i: -i["score"])
for _i, _x in enumerate(IDEAS):
    _x["rank"] = _i + 1

if __name__ == "__main__":
    print("\nIDEA RANKING")
    for i in IDEAS:
        print(f"  {i['rank']}. {i['name']:48s} +{i['attendees']:5.0f} attendees  Rs {i['spend']:>7,}  {i['per_1000']:.1f}/Rs1000 x conf {i['confidence']} x speed {i['speed']} = {i['score']:.1f}")
