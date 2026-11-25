# Growth Center: attendee growth for a Bengaluru college festival

Submission for the RISA Labs Growth APM assignment, **Challenge A (Attendee Growth)**.

**Vipluv Kumar** · Roll No. 22MF3IM22

| Deliverable | Where |
|---|---|
| Three-slide strategy PDF | [docs/Growth_Strategy_3_Slides.pdf](docs/Growth_Strategy_3_Slides.pdf) |
| Working product (dashboard, campaign and task management, embedded AI copilot) | **https://growth-center.onrender.com** (free hosting: the first load after a quiet spell takes up to a minute) |
| README | this file |
| Original data, kept for chatbot testing | [data/original/Attendee Dataset.xlsx](data/original/Attendee%20Dataset.xlsx) |

## Run it

```bash
python3 server.py            # Python 3.10+, no installs needed for the dashboard
# open http://localhost:8000
```

To turn on the AI copilot, give the server one key (a `.env` file works, see `.env.example`):

```bash
pip install -r requirements.txt && export ANTHROPIC_API_KEY=...   # Claude (default)
# or, with no install:
export GEMINI_API_KEY=...                                          # Gemini; the free AI Studio tier works
```

With no key the chat panel falls back to a small rule-based analyst and says so on screen. It handles the common questions from the same engine and declines the rest; it is a safety net, not the copilot.

Deploying for a public link:

- **Render** (what the live link uses): `render.yaml` is a blueprint; New > Blueprint, pick the repository, set the key under Environment. Any other host that runs `python3 server.py` works the same way; it reads `PORT`.
- **Vercel**: `vercel.json`, `api/dashboard.py` and `api/chat.py` are included (static files from `web/`, Python functions for the two endpoints). Set the key as an environment variable. *This configuration has not been deployed or tested; see Known limitations.*

Tests: `python3 tests/test_engine.py` and `python3 tests/test_copilot_loop.py`.

## The strategy in one paragraph

CampusFest 2025 (the provided dataset) drew **2,050 verified external attendees** against a goal of 2,200, on Rs 274,000. The money was in the wrong place: Paid Social and Creator Partners took 55% of spend and produced 25% of attendees, at Rs 295 each, and only half of the people they registered turned up. The five peer-led and organic channels delivered attendees at Rs 87. The plan for a Bengaluru festival doubles the budget to Rs 600,000, moves it to the channels that worked, pays for attendance instead of sign-ups, and adds a show-up programme. **Base case: about 4,600 verified attendees (2.2x). Stretch: about 5,900 (2.9x).**

## Research and data sources

| Claim | Source | Status |
|---|---|---|
| Bengaluru Urban has 1,106 colleges, the most of any district; Jaipur 703, Hyderabad 491, Pune 475 | AISHE 2021-22, as reported by [The Federal](https://thefederal.com/category/news/up-home-to-most-colleges-in-india-maharashtra-distant-second-107681), [Careers360](https://news.careers360.com/up-has-highest-number-of-colleges-in-country-followed-maharashtra-karnataka-aishe-report), [Statista](https://statista.com/statistics/1063133/india-number-of-colleges-by-major-district) | Sourced (secondary reports of the AISHE survey; one outlet gives Jaipur as 709) |
| Karnataka has 4,430 colleges and an estimated ~29.9 lakh higher-education enrolment | AISHE, as reported by [South First](https://thesouthfirst.com/pti/karnataka-has-3rd-highest-number-of-colleges-in-india-aishe-report/) and [Deccan Herald](https://www.deccanherald.com/education/karnataka-continues-to-record-highest-college-density-in-india-past-5-years-aishe-report-4067791) | Sourced (secondary) |
| ~750,000 college students in Bengaluru | 1,106 / 4,430 = 25% of colleges x 29.9 lakh | **Assumption.** No district enrolment figure was found; this assumes enrolment is proportional to college count |
| Every 2025 number (funnel, cost per attendee, show rates) | Provided Attendee Dataset, computed by `growth/engine.py` | Fact about a **synthetic** dataset |

Why Bengaluru: the highest college density in the country puts the most students within reach of one venue, and the cheapest channels in the data are peer-to-peer, which work best where campuses are close together.

## What the data says (facts)

Computed with the dataset's own rules: snapshot at end of day IST, import-retry duplicates removed (2 daily rows, 4 status versions, 20 check-ins), latest status per registration, external people only, and an attendee is a distinct external person with a check-in that is both admitted and verified.

| 2025, as of 20 Apr | Value |
|---|---|
| Impressions / clicks / landing sessions / form starts (anonymous events) | 1,029,015 / 32,070 / 24,645 / 5,548 |
| Identified external people | 3,625 (goal 3,600) |
| Registered | 2,800 (goal 3,200) |
| Confirmed | 2,500 |
| Verified attendees | 2,050 (goal 2,200): 1,925 registered + 125 walk-ins |
| Net spend | Rs 274,000 (budget Rs 300,000) |
| Cost per verified attendee | Rs 134 |

| Channel | Spend (Rs) | Registered | Attended | Rs per attendee | Registrants who attended |
|---|---|---|---|---|---|
| College Partnerships | 31,000 | 450 | 385 | 81 | 85.6% |
| Student Referrals | 19,000 | 350 | 275 | 69 | 78.6% |
| Organic Search | 14,000 | 250 | 195 | 72 | 78.0% |
| Community Groups | 16,000 | 200 | 165 | 97 | 82.5% |
| Campus Ambassadors | 42,000 | 520 | 390 | 108 | 75.0% |
| Paid Social | 93,000 | 680 | 340 | 274 | 50.0% |
| Creator Partners | 59,000 | 350 | 175 | 337 | 50.0% |

Attribution is the campaign recorded on the registration. It is a source relationship, not proof that the campaign caused the attendance.

## Assumptions

All of these live in `scripts/strategy_model.py` and can be changed there; the slides are generated from that file.

1. **Budget Rs 600,000 over 12 weeks**, twice the Rs 300,000 approved in 2025. The brief gives no budget.
2. **A new festival in Bengaluru converts like CampusFest 2025.** This is the largest assumption. The dataset is synthetic and names no city.
3. **Scaling penalty.** Channels grown 2-4x are modelled at 1.3-1.5x their 2025 cost per attendee (base) or 1.10-1.20x (stretch). This also stands in for audience overlap between the three peer ideas.
4. **Paid Social and Creators improve to 0.80-0.85x of 2025 cost** when restricted to retargeting and performance-paid micro-creators. Untested.
5. **Share of registrants who attend: 78% base, 82% stretch** (2025: 68.75% blended, 85.6% best channel). The plan's channel mix alone gives about 74%; the show-up programme is assumed to add the rest.
6. **Walk-ins: 6.5% of registered attendees** (the 2025 ratio) in the base case, 10% in the stretch.
7. **Capacity:** 35% of attendees come on both days (2025 fact); half of a day's crowd arrives in a 2-hour peak and a lane scans 400 people an hour (assumptions).
8. **40 partner colleges of about 2,500 students each.**
9. **Idea scores** use a confidence (0-1) and a speed factor that are judgement calls.

## Calculations

Run `python3 scripts/strategy_model.py` to print every number below.

Channel attendees = plan spend / (2025 cost per attendee x scaling factor). Registrations needed = attendees / that channel's 2025 registrant show rate. Upstream stages use the 2025 rates: 89.3% confirm, 11.4% registrations per landing session, 76.8% sessions per click, 3.12% click-through.

| | 2025 | Base | Stretch |
|---|---|---|---|
| Impressions | 1,029,015 | 2,025,624 | 2,400,372 |
| Landing sessions | 24,645 | 48,514 | 57,489 |
| Registered | 2,800 | 5,512 | 6,532 |
| Confirmed | 2,500 | 4,921 | 5,832 |
| Attended (registered) | 1,925 | 4,299 | 5,356 |
| Walk-ins | 125 | 279 | 536 |
| **Verified attendees** | **2,050** | **4,578** | **5,891** |
| Cost per attendee (Rs) | 134 | 131 | 102 |
| Peak-day attendance | 1,430 | 3,099 | 3,987 |

The base case therefore claims no efficiency gain over 2025: the same cost per attendee on twice the budget.

## Prioritisation framework

Score = attendees added per Rs 1,000 x confidence x speed of proof.

| Rank | Idea | Attendees | Budget (Rs) | Per Rs 1,000 | Confidence | Speed | Score |
|---|---|---|---|---|---|---|---|
| 1 | Referral rewards redeemed at the gate | +772 | 80,000 | 9.6 | 0.85 | 1.0 | 8.2 |
| 2 | Squad Pass through college clubs | +1,065 | 120,000 | 8.9 | 0.85 | 1.0 | 7.5 |
| 3 | Campus ambassadors paid per verified check-in | +1,000 | 140,000 | 7.1 | 0.85 | 1.0 | 6.1 |
| 4 | Show-up engine (reminders, re-confirm, waitlist backfill) | +215 | 30,000 | 7.2 | 0.70 | 0.6 | 3.0 |
| 5 | Paid social and creators rebuilt as retargeting | +529 | 130,000 | 4.1 | 0.50 | 1.0 | 2.0 |

Bets: double down on 1 and 2; scale 3 in steps; fund 4 in full despite its score, because it only scores low on speed of proof and it protects every registration the others buy; keep 5 small and cut it first. Rejected: cold paid reach and big-name creators, unattributable media (hoardings, radio, print), mass discount codes.

## The product

| Brief | Where in the app |
|---|---|
| 1. Measure | **Measure** tab: goals vs actuals, budget, forecast with its assumptions stated, awareness and people funnels, cumulative charts, campaign KPI table |
| 2. Diagnose | **Diagnose** tab: compare campaigns on any metric, step-by-step leak table against the all-campaign rate, last 14 days vs the 14 before |
| 3. Support decisions | **Decide** tab: SCALE / FIX / STOP / HOLD per campaign from editable thresholds, with evidence and a budget reallocation estimate |
| 4. Manage execution | **Execute** tab: campaigns (owner, status, budget, goal, add new) and tasks (owner, due date, status, priority, overdue). **Data** tab: log spend, activity and results, add target versions |
| 5. AI copilot | Right-hand panel on every tab |

The **dashboard date** in the header replays history: pick any day and every number is what the team would have known at the end of that day. Nothing later leaks in.

Changes are saved in the browser (`localStorage`) and sent with every request; the server recomputes all analytics from source data plus those changes, so the dashboard, the verdicts and the copilot always agree. Export and import of saved changes, and reset to the original data, are on the Data tab.

### How the copilot stays grounded

- It has no copy of the data in its prompt. It answers by calling tools that run on the same engine as the dashboard: `get_overview`, `get_campaign_performance`, `get_decisions`, `get_time_series`, `query_data` (filter, group and aggregate any table, for questions nobody anticipated), and `calculate` for arithmetic.
- Tools never return rows later than the dashboard date and apply the counting rules above.
- An unknown field returns an error listing the real fields, which is how it learns the data cannot answer something. The prompt lists what the dataset does not contain (demographics, colleges, revenue, unique reach, causation).
- Each answer has a "Data used" disclosure showing the queries it ran.
- Two guardrails are enforced in code, not left to the model: an answer that states figures in a turn where no tool was called is sent back once for a grounded retry, and so is an empty answer. Both were added after live testing showed the model doing exactly that.
- `propose_actions` drafts tasks or campaign changes as cards. Nothing is saved until the user clicks Confirm; the outcome is fed back to the model on the next turn.

### One complete workflow to demo

1. Set the dashboard date to **20 Mar**. Measure shows a projected shortfall against the 2,200 goal.
2. Decide shows Paid Social on STOP: Rs 348 per registration against Rs 111 blended.
3. Ask the copilot: *"Why is Paid Social on STOP, and what should we do with its budget?"* Then a follow-up: *"How does its cancellation rate compare with Student Referrals?"*
4. Ask: *"Create a task for Arjun to pause cold paid social and move the next tranche to referrals, due in 3 days."* Confirm the card; the task appears in Execute with its evidence.
5. Ask something the data cannot answer: *"Which college did most attendees come from?"*
6. Change the data: in Data, log Rs 20,000 of spend on Paid Social, or 200 new registrations on Student Referrals. Ask the first question again; the numbers move.

## Verification

Done:

- `tests/test_engine.py`: engine output matches figures computed independently with pandas from the workbook, at seven snapshot dates and per campaign, and checks that logged spend, results and new target versions change the right metrics on the right dates.
- `tests/test_copilot_loop.py`: the copilot's tool loop with a scripted stand-in for the model: tools see team changes, a missing field comes back as an error, proposals are returned for confirmation.
- All five tabs rendered in headless Chrome and inspected; the rule-based chat path exercised end to end in the browser.

- Live on the deployed site with Gemini (`gemini-3-flash-preview`, free tier): a metric question (2,050 visitors against a goal of 2,200, via `get_overview`), a question the data cannot answer (college of attendees), a task request (proposal card with owner, due date and evidence), and a question after changing the data (300 logged walk-ins moved the answer to 2,350 and "goal met").

Not done:

- The Claude path has never been run against the real API (no Anthropic key was available). Only the Gemini path has.
- The two guardrails were added after the live tests above and are covered by the scripted test only.
- Clicking through forms and dialogs was not automated; the pages were checked by rendering only.
- The Vercel configuration has not been deployed.

## Tools used

- **Claude Code** (Anthropic's coding agent) wrote the code, the strategy model, the slides and this README, and ran the verification above. Replace or extend this line with how you directed and reviewed the work.
- Python 3 standard library for the server and engine; the `anthropic` SDK for the Claude path; Gemini over REST.
- Build-time only: `openpyxl` (workbook to JSON, `scripts/build_data.py`), `reportlab` (slides, `scripts/build_slides.py "Your Name"`), pandas and PyMuPDF for checking.
- No templates or third-party UI libraries. Chart colours follow a published colour-blind-safe reference palette.

## Known limitations

- The live copilot runs on a free Gemini key. Newer Gemini models were over quota or busy for this key, so the app uses `gemini-3-flash-preview` and falls back through other models; under heavy testing the free allowance can run out, and the app then says the model is busy.

- Saved changes live in one browser. There are no accounts and no shared team state; a database (for example Supabase) would be the next step.
- The dataset is historical, so "live" operation is simulated by the dashboard date and by logging entries.
- Logged results are created as simulated people (IDs starting with `U`); logged check-ins against a campaign admit that campaign's confirmed registrants in ID order.
- The forecast is a straight-line projection with an assumed show rate. Replayed on 20 Mar 2025 it projected 1,597 attendees against an actual 2,050: registrations sped up afterwards and the actual show rate was 77%.
- Decision verdicts compare campaigns to the blended average, so one campaign will usually look worse than the rest; the minimum-sample rule and the evidence lines are there to keep that honest.
- "Registrations per landing session" divides people by anonymous sessions. It is a comparison index, not a person-level conversion rate.
- To test with a changed workbook, replace the file in `data/original/`, run `python scripts/build_data.py`, and restart; there is no in-app upload.
- Slides use "Rs" because the fonts on the build machine lack the rupee glyph.
