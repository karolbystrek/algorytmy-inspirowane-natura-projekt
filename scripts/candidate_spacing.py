import argparse
import copy
import csv
import json
import tempfile
from pathlib import Path

from agh_stations.model import Problem
from agh_stations.prepare_v2 import prepare
from agh_stations.solvers import optimal

VARIANTS = {
    "odstęp 35 m": {"spacing_m": 35},
    "odstęp 50 m": {"spacing_m": 50},
    "odstęp 70 m (wariant bazowy)": {},
    "odstęp 100 m": {"spacing_m": 100},
    "odstęp 140 m": {"spacing_m": 140},
    "do 300 m od popytu": {"max_walk_to_demand_m": 300},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", required=True)
    parser.add_argument("--config", default="configs/agh.json")
    parser.add_argument("--output", default="reports/results/candidate_spacing.csv")
    args = parser.parse_args()
    base = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        for index, (name, change) in enumerate(VARIANTS.items()):
            config = copy.deepcopy(base)
            config["candidates"].update(change)
            output = Path(folder) / str(index)
            output.mkdir()
            (output / "config.json").write_text(json.dumps(config), encoding="utf-8")
            prepare(output / "config.json", output, raw_dir=Path(folder) / "raw", pbf=args.pbf)
            problem = Problem.load(output / "problem.json")
            for p in (3, 5, 8, 15):
                result = optimal(problem, p)
                rows.append(
                    {
                        "variant": name,
                        "candidates": len(problem.candidate_ids),
                        "p": p,
                        "optimum_m": round(result.objective, 2),
                        "coverage": round(problem.metrics(result.selection)["coverage"], 4),
                    }
                )
    with Path(args.output).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
