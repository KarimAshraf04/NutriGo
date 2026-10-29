"""Recommender evaluation over all 101 foods (balanced goal, 1x portion).

Prints coverage, average kcal saved by the top swap and health-score gain,
and writes reports/recommender_eval.csv.
Run:  python evaluate.py
"""
import csv
import os

from nutrition import ROOT, load_alternatives, load_foods
from recommender import recommend


def evaluate(goal="balanced", foods=None, alts=None):
    foods = foods if foods is not None else load_foods()
    alts = alts if alts is not None else load_alternatives()
    rows = []
    for f in foods.values():
        eaten, swaps = recommend(f, alts, 1.0, goal, limit=4)
        top = swaps[0] if swaps else None
        rows.append({
            "food_id": f["food_id"], "category": f["category"], "kcal": f["kcal"],
            "health_score": eaten["health_score"], "n_swaps": len(swaps),
            "top_swap": top["name"] if top else "", "top_kcal": top["kcal"] if top else "",
            "kcal_saved": top["kcal_saved"] if top else "",
            "kcal_saved_pct": top["kcal_saved_pct"] if top else "",
            "health_gain": top["health_score"] - eaten["health_score"] if top else "",
        })
    covered = [r for r in rows if r["n_swaps"]]
    n = max(len(covered), 1)
    summary = {
        "coverage": f"{len(covered)}/{len(rows)}",
        "avg_kcal_saved": round(sum(r["kcal_saved"] for r in covered) / n),
        "avg_kcal_saved_pct": round(sum(r["kcal_saved_pct"] for r in covered) / n),
        "avg_health_gain": round(sum(r["health_gain"] for r in covered) / n),
        "no_swap": [r["food_id"] for r in rows if not r["n_swaps"]],
    }
    return rows, summary


if __name__ == "__main__":
    rows, s = evaluate()
    out = os.path.join(ROOT, "reports", "recommender_eval.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Coverage:          {s['coverage']} foods get at least one healthier swap")
    print(f"Top swap saves:    -{s['avg_kcal_saved']} kcal on average (-{s['avg_kcal_saved_pct']}%)")
    print(f"Health score:      +{s['avg_health_gain']} points gained by the top swap")
    print(f"No swap found for: {', '.join(s['no_swap']) or '-'}")
    print(f"Saved {out}")
