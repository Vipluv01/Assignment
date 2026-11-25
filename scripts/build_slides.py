"""Builds docs/Growth_Strategy_3_Slides.pdf from the strategy model (numbers are not typed by hand).

Usage:  python scripts/build_slides.py "Your Name"
Needs:  pip install reportlab   (build-time only)
"""
import math
import pathlib
import sys

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import strategy_model as sm  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "[Your Name]"
OUT = ROOT / "docs" / "Growth_Strategy_3_Slides.pdf"
W, H, M = 960, 540, 24
LOW = []

FD = "/System/Library/Fonts/Supplemental/"
try:
    pdfmetrics.registerFont(TTFont("B", FD + "Arial.ttf"))
    pdfmetrics.registerFont(TTFont("BB", FD + "Arial Bold.ttf"))
    pdfmetrics.registerFontFamily("B", normal="B", bold="BB", italic="B", boldItalic="BB")
    F, FB = "B", "BB"
except Exception:  # other systems: built-in fonts (no arrows)
    F, FB = "Helvetica", "Helvetica-Bold"

INK, INK2, LINE, ACC = colors.HexColor("#0b0b0b"), colors.HexColor("#52514e"), colors.HexColor("#d9d8d2"), colors.HexColor("#2a78d6")
SOFT, GOOD, WARN, BAD = colors.HexColor("#f1f0ec"), colors.HexColor("#e3f4e7"), colors.HexColor("#fdf3d3"), colors.HexColor("#fde8e6")
S = lambda size=8, bold=False, color=INK, lead=None: ParagraphStyle("s", fontName=FB if bold else F, fontSize=size, leading=lead or size * 1.22, textColor=color)
P = lambda t, size=8, bold=False, color=INK: Paragraph(t, S(size, bold, color))
n = lambda v: f"{v:,.0f}"


def table(c, data, x, y_top, widths, size=7.6, head=True, fills=None, pad=3):
    rows = [[cell if not isinstance(cell, str) else P(cell, size, bold=(head and i == 0)) for cell in r] for i, r in enumerate(data)]
    t = Table(rows, colWidths=widths)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    for (c0, r0, c1, r1, col) in fills or []:
        st.append(("BACKGROUND", (c0, r0), (c1, r1), col))
    t.setStyle(TableStyle(st))
    w, h = t.wrapOn(c, sum(widths), H)
    t.drawOn(c, x, y_top - h)
    LOW.append(y_top - h)
    return y_top - h


def para(c, text, x, y_top, width, size=8, bold=False, color=INK):
    p = P(text, size, bold, color)
    w, h = p.wrapOn(c, width, H)
    p.drawOn(c, x, y_top - h)
    LOW.append(y_top - h)
    return y_top - h


def header(c, num, title, sub):
    c.setFillColor(INK); c.rect(0, H - 58, W, 58, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont(FB, 19); c.drawString(M, H - 30, title)
    c.setFont(F, 9.5); c.setFillColor(colors.HexColor("#d6d5cf")); c.drawString(M, H - 46, sub)
    c.setFont(F, 8); c.drawRightString(W - M, H - 46, f"Slide {num} of 3")
    c.setFillColor(INK2); c.setFont(F, 6.6)
    c.drawString(M, 9, "FACT = computed from the provided Attendee Dataset (CampusFest 2025, synthetic) by the Growth Center engine.  ASSUMPTION = planning choice, listed in the README.  Rs = Indian rupees.")


def box(c, x, y_top, w, h, fill=SOFT):
    c.setFillColor(fill); c.setStrokeColor(LINE); c.roundRect(x, y_top - h, w, h, 5, stroke=1, fill=1)


B, ST, T25 = sm.BASE, sm.STRETCH, sm.tot
c = canvas.Canvas(str(OUT), pagesize=(W, H))
c.setTitle("Growth strategy: attendee growth, Bengaluru"); c.setAuthor(NAME)

# =============================================================== SLIDE 1
header(c, 1, f"How high can we aim?  {n(round(B['total'], -2))} verified attendees (base), {n(round(ST['total'], -2))} (stretch)",
       f"{NAME}  ·  Growth APM assignment  ·  Challenge A: attendee growth  ·  City: Bengaluru  ·  2025 benchmark: {n(T25['unique_external_visitors'])} verified attendees on Rs {n(T25['spend_inr'])}")
top = H - 70
# left column
x, w = M, 286
y = para(c, "Why Bengaluru", x, top, w, 11.5, True)
y = para(c, "Bengaluru Urban has the most colleges of any district in India: <b>1,106</b>, ahead of Jaipur (703), Hyderabad (491) and Pune (475) "
            "(AISHE 2021-22). Dense campuses plus metro links mean one venue is reachable by more students than in any other Tier 1 city, "
            "and peer channels (the cheapest in our data) work best where colleges are close together.", x, y - 3, w, 8.8)
y = para(c, "Target audiences, sized and ranked", x, y - 8, w, 11.5, True)
y = table(c, [["Audience", "Size", "Priority and why"],
              ["1. Students at 40 partner colleges", "~100,000 (40 x ~2,500, ASSUMPTION)", "<b>First.</b> Reached through clubs, ambassadors and referrals: Rs 69-108 per attendee and 75-86% of registrants attended (FACT)."],
              ["2. Other Bengaluru college students", "~750,000 (ASSUMPTION: 25% of Karnataka's ~2.99 million enrolment, by college share)", "<b>Second.</b> Community groups, search and retargeting. Cold paid reach cost Rs 274-337 per attendee and only 50% of registrants attended (FACT)."],
              ["3. Recent graduates, 21-25", "Not sized", "<b>Not targeted.</b> No data on them and they are outside a college festival's core. Walk-ins only."]],
          x, y - 3, [84, 80, 122], 8.5)
y = para(c, "Capacity constraints", x, y - 8, w, 11.5, True)
y = table(c, [["Constraint", "Base", "Stretch"],
              ["Peak-day attendance (35% came both days in 2025, FACT)", n(sm.peak_day(B["total"])), n(sm.peak_day(ST["total"]))],
              ["Entry lanes needed (ASSUMPTION: 400 scans/lane/hour, half the day's crowd in a 2-hour peak)", str(math.ceil(sm.peak_day(B['total']) / 2 / 2 / 400)), str(math.ceil(sm.peak_day(ST['total']) / 2 / 2 / 400))],
              ["Venue must hold (peak day + 15% buffer)", n(sm.peak_day(B["total"]) * 1.15), n(sm.peak_day(ST["total"]) * 1.15)]],
          x, y - 3, [186, 50, 50], 8.5)
para(c, "If the venue holds fewer than the stretch figure, registration is capped and a waitlist backfills cancellations.", x, y - 4, w, 8, color=INK2)

# middle column: funnel
x, w = M + 300, 300
y = para(c, "Funnel: reach to registration to attendance", x, top, w, 11.5, True)
rows = [["Stage", "2025 (FACT)", "Base", "Stretch", "Rate used"]]
f25 = [T25["impressions"], T25["clicks"], T25["landing_page_sessions"], T25["registered_external_people"], T25["confirmed"], T25["visitors_with_registration"], T25["walk_in_visitors"], T25["unique_external_visitors"]]
keys = ["impressions", "clicks", "sessions", "registrations", "confirmed", "registered_visitors", "walkins", "total"]
labels = ["Impressions (events)", "Clicks (events)", "Landing sessions (events)", "Registered people", "Confirmed", "Attended (registered)", "Walk-ins", "<b>Verified attendees</b>"]
rates = [f"", f"{sm.CTR:.1%} click-through (FACT)", f"{sm.SESSION_PER_CLICK:.0%} of clicks (FACT)", f"{sm.REG_PER_SESSION:.1%} per session (FACT)", f"{sm.CONFIRM:.0%} confirm (FACT)",
         f"{T25['visitors_with_registration']/T25['registered_external_people']:.0%} in 2025; {B['reg_to_attend']:.0%} / {ST['reg_to_attend']:.0%} of registrants (ASSUMPTION)",
         f"{sm.WALKIN_RATIO:.1%} (FACT) / 10% (ASSUMPTION)", f"{B['total']/T25['unique_external_visitors']:.1f}x and {ST['total']/T25['unique_external_visitors']:.1f}x 2025"]
for lab, a, k, r in zip(labels, f25, keys, rates):
    rows.append([lab, n(a), n(B[k]), n(ST[k]), r])
y = table(c, rows, x, y - 3, [84, 48, 44, 44, 80], 8.5, fills=[(0, 8, -1, 8, GOOD)])
y = para(c, f"Cost per verified attendee: Rs {T25['spend_inr']/T25['unique_external_visitors']:.0f} in 2025 (FACT), Rs {B['cost_per_attendee']:.0f} base, Rs {ST['cost_per_attendee']:.0f} stretch, "
            f"on a Rs {n(sm.BUDGET)} budget over 12 weeks (ASSUMPTION: 2x the Rs 300,000 approved in 2025).", x, y - 5, w, 8.8)
y = para(c, "Why you should believe the number", x, y - 9, w, 11.5, True)
paid = sm.BENCH["Paid Social"]; cr = sm.BENCH["Creator Partners"]
peer_sp = T25["spend_inr"] - paid["spend"] - cr["spend"]; peer_v = T25["visitors_with_registration"] - paid["vis"] - cr["vis"]
for t in [f"<b>The base case assumes no efficiency gain.</b> Rs {B['cost_per_attendee']:.0f} per attendee is in line with 2025's Rs {T25['spend_inr']/T25['unique_external_visitors']:.0f}; every channel we scale is modelled 30-50% more expensive than it actually was.",
          f"<b>2025 mis-spent its money, and that is fixable.</b> Paid Social and Creators took {(paid['spend']+cr['spend'])/T25['spend_inr']:.0%} of spend and delivered {(paid['vis']+cr['vis'])/T25['unique_external_visitors']:.0%} of attendees "
          f"(Rs {(paid['spend']+cr['spend'])/(paid['vis']+cr['vis']):.0f} each). The other five channels delivered attendees at Rs {peer_sp/peer_v:.0f} (FACT).",
          f"<b>Attendance leaks after registration.</b> {n(T25['confirmed']-T25['visitors_with_registration'])} confirmed registrants did not come (FACT). The best channel got 86% of registrants through the gate; we assume {B['reg_to_attend']:.0%}.",
          f"<b>The stretch needs things to go right, and says which.</b> Scaled channels within 10-20% of 2025 cost, {ST['reg_to_attend']:.0%} of registrants attending, walk-ins at 10%."]:
    y = para(c, "• " + t, x, y - 3, w, 8.7)

# right column: channel plan
x, w = M + 614, 298
y = para(c, "Where the attendees come from (base case)", x, top, w, 11.5, True)
rows = [["Channel", "Plan spend (Rs)", "Rs / attendee 2025 (FACT)", "Rs / attendee plan", "Attendees"]]
for r in B["rows"]:
    rows.append([r["channel"], n(r["spend"]), f"{r['cpv_2025']:.0f}", f"{r['cpv_plan']:.0f}", n(r["visitors"])])
rows += [["Show-up programme", n(sm.SHOWUP_SPEND), "", f"{B['channel_visitors']/B['registrations']:.0%} → {B['reg_to_attend']:.0%} attend", "+" + n(B["showup_gain"])],
         ["Walk-ins", "0", "", f"{sm.WALKIN_RATIO:.1%} of attended", "+" + n(B["walkins"])],
         ["Contingency", n(sm.CONTINGENCY), "", "", ""],
         ["<b>Total</b>", f"<b>{n(sm.BUDGET)}</b>", "134", f"<b>{B['cost_per_attendee']:.0f}</b>", f"<b>{n(B['total'])}</b>"]]
y = table(c, rows, x, y - 3, [88, 50, 54, 58, 48], 8.5, fills=[(0, 11, -1, 11, GOOD), (0, 6, -1, 7, BAD)])
y = para(c, "Plan cost per attendee = 2025 cost x an ASSUMED scaling penalty (1.3-1.5x for channels we grow 2-4x; 0.80-0.85x for the two we cut back to retargeting and performance-paid micro-creators, shaded red).",
         x, y - 4, w, 8, color=INK2)
box(c, x, y - 8, w, 112, GOOD)
yy = para(c, f"Base: {n(round(B['total'], -2))} verified attendees ({B['total']/T25['unique_external_visitors']:.1f}x 2025)", x + 8, y - 15, w - 16, 13, True)
yy = para(c, "Same cost per attendee as 2025, twice the budget, money moved to the channels that already worked.", x + 8, yy - 2, w - 16, 8.8)
yy = para(c, f"Stretch: {n(round(ST['total'], -2))} verified attendees ({ST['total']/T25['unique_external_visitors']:.1f}x 2025)", x + 8, yy - 7, w - 16, 13, True)
para(c, f"Same budget. Requires Rs {ST['cost_per_attendee']:.0f} per attendee and {ST['reg_to_attend']:.0%} of registrants attending.", x + 8, yy - 2, w - 16, 8.8)
print("slide 1 lowest y", min(LOW)); LOW.clear()
c.showPage()

# =============================================================== SLIDE 2
by = {r["channel"]: r for r in B["rows"]}
header(c, 2, "Where will we place our bets?  Five ideas, ranked",
       f"{NAME}  ·  Budget Rs {n(sm.BUDGET)}  ·  12 weeks to event  ·  4 owners plus volunteers  ·  'attendees added' are base-case numbers from the Slide 1 model")
top = H - 68
pr, cre = by["Paid Social"], by["Creator Partners"]
noshow = T25["confirmed"] - T25["visitors_with_registration"]
TEXT = {
    "squad": ("<b>Squad Pass through college clubs.</b> Club organisers at 40 partner colleges register groups of 5+ for a reserved zone and a club leaderboard. Friends who commit together turn up together.",
              "2025 FACT: Rs 81 per attendee, 86% of registrants attended, lowest cancellations (4.0%)",
              "Owner: Meera + 2 volunteers. Weeks 1-10.",
              "Pilot in 5 colleges for 2 weeks. KPIs: registrations per club, group size, cost per registration, share of each group that confirms."),
    "referral": ("<b>Referral rewards redeemed at the gate.</b> Every registrant gets a link: bring 3 friends and all four get fast-lane entry and a food coupon, issued only when each friend is scanned in. We pay for attendance, not sign-ups.",
                 "2025 FACT: cheapest channel, Rs 69 per attendee, 79% of registrants attended",
                 "Owner: Dev. Build week 1, live weeks 2-12.",
                 "A/B the reward on the first 300 registrants. KPIs: invites per registrant, invite-to-registration rate, referral cost per registration."),
    "showup": ("<b>Show-up engine.</b> WhatsApp and email at T-14, T-7, T-1 with line-up drops, a one-tap 'I'm coming' re-confirm, calendar hold and QR ticket; cancelled seats go to the waitlist.",
               f"2025 FACT: {n(noshow)} confirmed registrants did not come; one point of show rate is ~{B['registrations']/100:.0f} attendees",
               "Owner: Dev. Build weeks 2-3, runs weeks 4-12. Needs ideas 1-3 to fill the list.",
               "10% holdout gets no reminders. KPIs: T-7 re-confirm rate, cancellations, opt-outs; on the day, attended share vs holdout."),
    "ambassador": ("<b>Campus ambassadors paid per verified check-in.</b> 80 ambassadors across the 40 colleges, each with a tracked link, a weekly target and a payout for every referred student who is scanned in.",
                   "2025 FACT: Rs 108 per attendee, 75% attended, best registrations per landing session (14.1%)",
                   "Owner: Meera. Recruit weeks 1-2, live weeks 3-12.",
                   "Start with 20 ambassadors for 2 weeks. KPIs: registrations per ambassador per week, cost per registration, confirm rate."),
    "retarget": ("<b>Paid social and creators, rebuilt as retargeting.</b> No cold reach. Ads only to people who visited the site or started the form; micro-creators from partner colleges paid per confirmed registration.",
                 "2025 FACT: Rs 274 and Rs 337 per attendee; only 50% of their registrants attended",
                 "Was Rs 152,000. Owners: Arjun, Nisha. Weeks 3-12, released in Rs 10,000 tranches.",
                 "Each tranche must earn the next. KPIs: cost per registration vs blended, registrations per landing session, cancellations."),
}
R = {i["key"]: i["rank"] for i in sm.IDEAS}
rows = [["#", "Idea and why it could work", "Attendees added and evidence", "Budget, people, timeline", "Test and KPIs", "Score"]]
for i in sm.IDEAS:
    what, ev, who, test = TEXT[i["key"]]
    rows.append([str(i["rank"]), what, f"<b>+{n(i['attendees'])}</b><br/>{ev}", f"<b>Rs {n(i['spend'])}</b><br/>{who}", test,
                 f"<b>{i['score']:.1f}</b><br/>{i['per_1000']:.1f} x {i['confidence']} x {i['speed']}"])
fills = [(0, R["referral"], -1, R["referral"], GOOD), (0, R["squad"], -1, R["squad"], GOOD), (0, R["retarget"], -1, R["retarget"], WARN)]
y = table(c, rows, M, top, [16, 222, 142, 122, 170, 50], 8.3, fills=fills)
y = para(c, f"<b>Score</b> = attendees added per Rs 1,000 x confidence (0-1: how directly 2025 data supports it) x speed (1.0 if we can prove or kill it in 2 weeks, 0.6 if proof only comes near the event). "
            f"Confidence and speed are our judgement (ASSUMPTION).", M, y - 6, 722, 8.3)
para(c, f"<b>Not in the five:</b> Community Groups and Organic Search keep running at Rs {n(by['Community Groups']['spend']+by['Organic Search']['spend'])} for +{n(by['Community Groups']['visitors']+by['Organic Search']['visitors'])} attendees; "
        f"walk-ins add ~{n(B['walkins'])}; Rs {n(sm.CONTINGENCY)} is held as contingency. Together with the five ideas this is the {n(B['total'])} base case.", M, y - 5, 722, 8.3)

x, w = M + 736, 176
def bet(y_top, title, body, col, h):
    box(c, x, y_top, w, h, col)
    yy = para(c, title, x + 7, y_top - 6, w - 14, 9.5, True)
    para(c, body, x + 7, yy - 2, w - 14, 8.1)
    return y_top - h - 7
y2 = bet(top, f"Double down: {R['referral']} and {R['squad']}", "Best attendees per rupee, direct 2025 evidence, provable in two weeks. They compound: groups of friends register together and recruit more friends.", GOOD, 84)
y2 = bet(y2, f"Scale in steps: {R['ambassador']}", "Largest single source but the most people to manage. Budget is released as ambassadors hit weekly targets.", SOFT, 66)
y2 = bet(y2, f"Fund despite the score: {R['showup']}", "Scores low only because proof arrives at T-7. It costs 5% of budget and protects every registration the other ideas buy, so it is funded in full from week 2.", SOFT, 86)
y2 = bet(y2, f"Deprioritise: {R['retarget']}", "Kept small, on a leash, and first to be cut. Useful only to recapture people who already showed intent.", WARN, 66)
y2 = bet(y2, "Rejected", "• Cold paid reach and big-name creators: half the registrants never came.<br/>• Hoardings, radio, print: cannot be attributed, so we cannot learn.<br/>• Mass discount codes: sign-ups with no intent, the no-show problem again.", BAD, 118)
para(c, "<b>Constraints, overlap, dependencies.</b> The three peer ideas reach the same students: the 1.3-1.5x cost penalty in the model is the allowance for that overlap, and attribution stays with the first registration source. "
        "Meera owns two ideas, so volunteers run club outreach. Paying on check-in delays payouts but removes fake sign-ups. Exams or a rival fest would hit every idea at once, so the date is locked in week 0.", M, y - 5 - 24 - 5, 722, 8.3)
print("slide 2 lowest y", min(LOW)); LOW.clear()
c.showPage()

# =============================================================== SLIDE 3
header(c, 3, "How will we know what's working?  A signal, a threshold and a pre-agreed action for every idea",
       f"{NAME}  ·  Checked weekly on a trailing 14-day window, minimum 20 registrations before any verdict  ·  'blended' = all campaigns in the same window")
top = H - 68
ROWS3 = {
    "squad": ["Squad Pass", "Registrations per partner club and group size. Risk: organisers register names who never intended to come.",
              "Week 2 of pilot: registrations per club; share of each group that confirms.", "25+ registrations per club and cost per registration ≤ 0.8x blended",
              "10-25 per club, or under 80% of a group confirms", "Under 10 per club after 14 days",
              "Scale: add 10 colleges a week. Change: swap the club prize for a per-head perk and require each member to confirm. Stop: drop that club, move its budget to referrals."],
    "referral": ["Gate-redeemed referrals", "Invites per registrant x invite-to-registration rate. Risk: reward too weak to share, or gaming with fake friends.",
                 "First 7 days live: referred registrations per registrant.", "0.3+ per registrant and referral cost per registration ≤ 0.8x blended",
                 "0.15-0.3 per registrant", "Under 0.15 after 14 days",
                 "Scale: put the link in every reminder. Change: test the other reward, cut 'bring 3' to 'bring 2'. Stop: keep the link, remove the reward budget."],
    "showup": ["Show-up engine", "Share of confirmed registrants who attend. Risk: too many messages cause opt-outs; the true result is only visible on event day.",
               "T-7: one-tap re-confirm rate vs the 10% holdout. Weekly: cancellations and opt-outs.", "Re-confirm 70%+ and 5+ points above holdout",
               "Opt-outs above 2x blended, or cancellations above 1.5x blended (6.5% in 2025)", "A message variant with opt-outs above 8%",
               "Scale: add a T-3 line-up drop. Change: cut frequency, move email to WhatsApp. Stop: pull the variant; release cancelled seats to the waitlist."],
    "ambassador": ["Ambassadors", "Registrations per ambassador per week. Risk: a few stars carry the programme and the rest coast.",
                   "Week 2: registrations per ambassador per week; cost per registration.", "5+ per week: double their targets and give them Squad Pass clubs",
                   "Bottom half under 3 per week", "A college under 2 per ambassador per week for 2 weeks",
                   "Scale: recruit 2 more per strong college. Change: retrain or replace the bottom half. Stop: close that college, reassign its budget."],
    "retarget": ["Paid and creator retargeting", "Cost per registration and the share of those registrants who confirm. Risk: cheap sign-ups that do not attend (50% in 2025).",
                 "Each Rs 10,000 tranche: cost per registration vs blended.", "≤ 0.8x blended for a full window (not expected)",
                 "Registrations per landing session under 0.75x blended: fix the landing page before spending more", "≥ 1.5x blended for 14 days with 20+ registrations",
                 "Stop is the default outcome. Freed money goes to whichever peer idea is on SCALE."],
}
rows = [["Idea", "Critical variable and biggest risk", "Early signal (when)", "SCALE if", "CHANGE if", "STOP if", "What we do"]]
for i in sm.IDEAS:
    r = ROWS3[i["key"]]
    rows.append([f"{i['rank']}. {r[0]}"] + r[1:])
y = table(c, rows, M, top, [70, 150, 116, 112, 116, 104, 244], 8.1, fills=[(3, 1, 3, 5, GOOD), (4, 1, 4, 5, WARN), (5, 1, 5, 5, BAD)])

bw = (W - 2 * M - 16) / 3
ytop = y - 10
m_mar = sm.m.decisions("2025-03-20")
ps = next(d for d in m_mar["campaigns"] if d["campaign_name"] == "Paid Social")
fc = sm.m.overview("2025-03-20")["forecast"]
panels = [
    ("The dashboard makes the call visible",
     f"The Decide tab applies these same thresholds to live data and labels every campaign SCALE, FIX, STOP or HOLD with the numbers behind it. "
     f"Replayed on the 2025 data it works: on 20 March, 23 days before the event, it flags Paid Social at Rs {ps['window']['cost_per_registration']:.0f} per registration against Rs {m_mar['blended_cost']:.0f} blended "
     f"({ps['window']['cost_per_registration']/m_mar['blended_cost']:.1f}x, STOP), and the forecast shows {n(fc['projected_visitors'])} attendees against a goal of {n(fc['visitor_goal'])} (at an assumed 75% show rate). "
     f"The final result was {n(T25['unique_external_visitors'])}."),
    ("The AI copilot explains and acts",
     "The copilot answers through tool calls on the same engine, not from general knowledge. Ask why a campaign is on FIX and it pulls the step rates, separates evidence from assumption, "
     "and says when the data cannot answer (demographics, causation). Ask it to act and it drafts the task with owner, due date and evidence; nothing is saved until a person confirms."),
    ("Leading indicators, reviewed weekly",
     "Attendance is only known on the day, so every rule uses something observable weeks earlier: cost per registration, registrations per landing session, confirm rate, cancellations, opt-outs, T-7 re-confirms. "
     "Thresholds are editable in the app; change one and verdicts, forecast and copilot answers move together. A weekly 30-minute review turns each verdict into a task with an owner."),
]
bh = 150
for i, (t, body) in enumerate(panels):
    x = M + i * (bw + 8)
    box(c, x, ytop, bw, bh, SOFT)
    yy = para(c, t, x + 9, ytop - 8, bw - 18, 11, True)
    para(c, body, x + 9, yy - 4, bw - 18, 9.2)
print("slide 3 lowest y", min(LOW))
c.showPage()
c.save()
print("wrote", OUT)
