import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from payload_stash.config_utility import evaluate_expect, _apply_matcher

BODY = json.dumps({
    "state": {
        "inventoryItems": [
            {"id": "missionA", "customData": [{"key": "progress", "value": 25},
                                              {"key": "completed", "value": True}]},
            {"id": "missionB", "customData": [{"key": "difficulty", "value": "easy"}]},
        ],
        "team": ["u1", "u2", "u3", "u4", "u5"],
        "tier": "3",
    }
})

def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond

def run():
    ok = True
    # --- new matchers (unit) ---
    ok &= check("in",        _apply_matcher("in", "3", ["1", "2", "3"])[0] is True)
    ok &= check("notIn",     _apply_matcher("notIn", "9", ["1", "2", "3"])[0] is True)
    ok &= check("lengthEq",  _apply_matcher("lengthEquals", ["a", "b", "c"], 3)[0] is True)
    ok &= check("lengthGte", _apply_matcher("lengthGte", ["a", "b", "c"], 2)[0] is True)
    ok &= check("lengthLte", _apply_matcher("lengthLte", ["a", "b"], 5)[0] is True)
    ok &= check("lengthFail", _apply_matcher("lengthEquals", ["a"], 3)[0] is False)
    # --- jsonpath in Expect (integration via evaluate_expect) ---
    res = evaluate_expect([
        {"$.state.inventoryItems[?(@.id=='missionA')].customData[?(@.key=='progress')].value": {"equals": 25}},
        {"$.state.inventoryItems[?(@.id=='missionA')].customData[?(@.key=='completed')].value": {"equals": True}},
        {"$.state.inventoryItems[?(@.id=='missionB')].customData[?(@.key=='completed')].value": {"exists": False}},
        {"$.state.team[*]::count": {"equals": 5}},
        {"$.state.team": {"lengthEquals": 5}},
        {"$.state.tier": {"in": ["1", "2", "3"]}},
        {"status": 200},                       # plain path still works
    ], 200, {}, BODY, 12)
    for label, passed, detail in res:
        ok &= check(label, passed)
    print("\nALL GREEN" if ok else "\nRED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    run()
