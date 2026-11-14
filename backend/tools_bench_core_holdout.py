"""Pilot comparing v4, v5 and v6 on matched, unseen synthetic opponent cores."""
import argparse
import json
import os
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter


def run(path):
    from app import auto_team, battle_lab, collector, parallel, regulation
    from app.engine import Engine

    engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    fmt, games = "Doubles", 27
    modes = ("v4", "v5", "v6")
    styles = (*auto_team.SELECT_STYLES, "counter")
    conditions = (("rain", ["rain"]), ("trickroom", ["trickroom"]))
    output = {"method": "matched-opponents pilot; fixed quick settings; measured wall time, not an equal-time experiment",
              "pool": "audit", "seed": 79_651_061, "gamesPerCandidate": games, "cpu": "master",
              "cpuStyles": styles, "data": regulation.provenance(engine.d), "conditions": []}
    for idx, (label, preferences) in enumerate(conditions):
        row = {"condition": label, "engines": {}, "comparisons": {}}
        teams, plans, owners = [], [], []
        for mode in modes:
            start = perf_counter()
            result = auto_team.build(engine, fmt, preferences, [], [], depth="quick", tune="off",
                                     rankers=False, engine=mode)
            candidates = result["candidates"]
            row["engines"][mode] = {"seconds": round(perf_counter() - start, 2), "candidates": []}
            for candidate in candidates:
                teams.append([member["set"] for member in candidate["members"]])
                plans.append((candidate.get("metrics") or {}).get("policyMap"))
                owners.append(mode)
            print(label, mode, len(candidates), row["engines"][mode]["seconds"], flush=True)
        reports = parallel.compare_teams(engine, fmt, teams, games, output["seed"] + idx, "master",
                                         policies=plans, cpu_styles=styles, split="audit")
        cores = reports[0]["opponentCores"]
        assert all(report["opponentCores"] == cores for report in reports)
        row["cores"] = cores
        grouped = {mode: [] for mode in modes}
        for mode, team, report in zip(owners, teams, reports, strict=True):
            grouped[mode].append(report["outcomes"])
            row["engines"][mode]["candidates"].append({"members": [s["id"] for s in team],
                                                        "outcomes": report["outcomes"],
                                                        "rate": mean(report["outcomes"])})
        matched = {mode: list(map(mean, zip(*group))) for mode, group in grouped.items()}
        for mode, outcomes in matched.items():
            if mode == "v4":
                continue
            delta = [b - a for a, b in zip(matched["v4"], outcomes, strict=True)]
            row["comparisons"][f"{mode}-v4"] = {"delta": mean(delta), "ci": battle_lab.core_interval(delta, cores)}
        output["conditions"].append(row)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        os.environ["RESEARCH_DB"] = str(Path(temp) / "research.sqlite")
        run(args.output)
        from app.research import LAB

        LAB.db().close()
