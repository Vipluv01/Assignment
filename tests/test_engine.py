"""Checks the engine against numbers computed independently with pandas from the workbook
(see README > Verification). Run:  python3 tests/test_engine.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from growth.engine import Model, calculate

m = Model()
EXPECT = {  # as_of: (identified, registered, confirmed, cancelled, visitors, spend)
    "2025-02-15": (1055, 587, 426, 30, 0, 73475),
    "2025-03-14": (2329, 1506, 1255, 106, 0, 189575),
    "2025-03-31": (3320, 2337, 1962, 154, 0, 248150),
    "2025-04-11": (3500, 2800, 2500, 183, 0, 276500),
    "2025-04-12": (3580, 2800, 2500, 183, 1430, 276500),
    "2025-04-13": (3625, 2800, 2500, 183, 2050, 276500),
    "2025-04-20": (3625, 2800, 2500, 183, 2050, 274000),
}
for d, exp in EXPECT.items():
    x = m.metrics(d)
    got = (x["identified_external_people"], x["registered_external_people"], x["confirmed"], x["cancelled"], x["unique_external_visitors"], x["spend_inr"])
    assert got == exp, (d, got, exp)
assert m.duplicates_removed["daily"] == 2 and m.duplicates_removed["registration_history"] == 4 and m.duplicates_removed["checkins"] == 20
CAMP = {"C01": (520, 390, 42000), "C02": (680, 340, 93000), "C03": (350, 175, 59000), "C04": (450, 385, 31000), "C05": (350, 275, 19000), "C06": (250, 195, 14000), "C07": (200, 165, 16000)}
t = {r["campaign_id"]: r for r in m.campaign_table("2025-04-20")}
for cid, (reg, vis, spend) in CAMP.items():
    assert (t[cid]["registered_external_people"], t[cid]["unique_external_visitors"], t[cid]["spend_inr"]) == (reg, vis, spend), cid
assert t[None]["unique_external_visitors"] == 125
f = m.metrics("2025-04-20")
assert (f["impressions"], f["clicks"], f["landing_page_sessions"], f["registration_starts"]) == (1029015, 32070, 24645, 5548)
assert f["visitors_with_registration"] == 1925 and f["show_rate_confirmed"] == 0.77
ts = m.time_series("2025-04-20")
assert ts[-1]["cum_registrations"] == 2800 and ts[-1]["cum_visitors"] == 2050 and ts[-1]["cum_spend_inr"] == 274000

# team changes flow through every metric
ov = {"daily": [{"activity_id": "USR-1", "campaign_id": "C02", "activity_date": "2025-03-01", "marketing_spend_inr": 5000, "landing_page_sessions": 100}],
      "outcomes": [{"id": "O1", "campaign_id": "C05", "date": "2025-03-01", "new_leads": 3, "new_registrations": 10, "verified_checkins": 0},
                   {"id": "O2", "campaign_id": None, "date": "2025-04-13", "verified_checkins": 5}],
      "targets": [{"effective_at": "2025-04-01T09:00:00", "identified_external_people_goal": 4000, "registration_goal": 3500, "unique_external_visitors_goal": 2500, "marketing_budget_inr": 320000, "target_version": "Test"}]}
m2 = Model(ov); y = m2.metrics("2025-04-20")
assert y["spend_inr"] == 279000 and y["registered_external_people"] == 2810 and y["identified_external_people"] == 3625 + 13 + 5 and y["unique_external_visitors"] == 2055
assert m2.metrics("2025-02-28")["registered_external_people"] == m.metrics("2025-02-28")["registered_external_people"]
assert m2.overview("2025-04-20")["vs_target"]["unique_external_visitors"]["goal"] == 2500 and m2.overview("2025-03-20")["vs_target"]["unique_external_visitors"]["goal"] == 2200

q = m.query({"table": "checkins", "filters": [{"field": "result", "op": "eq", "value": "denied"}], "aggregates": [{"op": "count"}, {"op": "count_distinct", "field": "person_id"}]}, "2025-04-20")
assert q["rows"][0]["count"] == 50, q
assert "error" in m.query({"table": "people", "group_by": ["college"]}, "2025-04-20")
q = m.query({"table": "registrations", "filters": [{"field": "person_type", "value": "external"}], "group_by": ["week(registered_at)"], "aggregates": [{"op": "count"}], "order_by": [{"field": "week(registered_at)"}]}, "2025-04-20")
assert sum(r["count"] for r in q["rows"]) == 2800 and q["rows"][0]["count"] == 36
assert calculate("274000/2050") == 274000 / 2050
for d in ("2025-02-01", "2025-03-14", "2025-04-20"):
    dec = m.decisions(d); ov_ = m.overview(d)
    print(d, ov_["phase"], {c["campaign_name"]: c["verdict"] for c in dec["campaigns"]}, "| forecast visitors", ov_["forecast"]["projected_visitors"], dec["reallocation"] and dec["reallocation"]["net_registrations_est"])
print("all engine checks passed")
