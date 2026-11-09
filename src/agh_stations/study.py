"""The full experiment protocol from docs/EXPERIMENTS.md, as one repeatable offline command.

ABC settings are chosen on a separate development instance, so tuning never looks at the dataset
used for the reported ranking. Every optimum is proved with the integer program.
"""

import csv
import hashlib
import json
import platform
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import __version__ as scipy_version
from scipy.sparse.csgraph import dijkstra
from scipy.stats import mannwhitneyu

from agh_stations.audit import write_json
from agh_stations.model import Problem
from agh_stations.routing import read_walk_edges, walking_matrix
from agh_stations.solvers import greedy_construction_cost, optimal, solve

THRESHOLDS = (150, 250, 350)
FOODS = (8, 12, 24)
LIMIT_RULES = ("15", "30", "60", "foods*p")


def limit_value(rule, foods, p):
    return foods * p if rule == "foods*p" else int(rule)


def write_rows(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_development_instance(dataset_dir, output_dir, n=60, m=150, seed=2026):
    """Random points on the real graph: realistic geometry, unrelated to the reported instance."""
    dataset_dir, output_dir = Path(dataset_dir), Path(output_dir)
    graph, nodes, _ = walking_matrix(read_walk_edges(dataset_dir / "map.geojson"))
    rng = np.random.default_rng(seed)
    demand = rng.choice(len(nodes), n, replace=False)
    candidates = rng.choice(len(nodes), m, replace=False)
    distances = dijkstra(graph, directed=True, indices=demand)[:, candidates]
    weights = rng.integers(1, 6, n).astype(float)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "problem.json",
        {
            "schema_version": 1,
            "dataset_id": f"agh-development-seed{seed}",
            "purpose": "Tuning only. Random points and weights; never report as a campus result.",
            "candidates": [{"id": f"dev-candidate-{j}"} for j in range(m)],
            "demand": [{"id": f"dev-demand-{i}"} for i in range(n)],
            "distances_m": np.round(distances, 3).tolist(),
            "scenarios": {"development": weights.tolist()},
            "scenario_mixture": {"development": 1},
        },
    )


def holm(p_values):
    """Holm-Bonferroni adjusted p-values, in the input order."""
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def summarize(values):
    values = np.asarray(values, dtype=float)
    return {
        "best_m": float(values.min()),
        "mean_m": float(values.mean()),
        "std_m": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "median_m": float(np.median(values)),
        "q25_m": float(np.quantile(values, 0.25)),
        "q75_m": float(np.quantile(values, 0.75)),
    }


def gap(value, reference):
    return 100 * (value - reference) / reference if reference else float(value - reference)


def tune(problem, ps, budget, runs):
    """Grid of colony size and abandonment limit, then an ablation of the two ABC mechanisms."""
    rows = []
    for p in ps:
        best = optimal(problem, p).objective
        for foods in FOODS:
            for rule in LIMIT_RULES:
                limit = limit_value(rule, foods, p)
                values = [
                    solve(problem, "abc", p, budget, seed, foods=foods, limit=limit).objective
                    for seed in range(runs)
                ]
                rows.append(
                    {
                        "experiment": "grid",
                        "p": p,
                        "foods": foods,
                        "limit_rule": rule,
                        "limit": limit,
                        "peer_probability": 0.5,
                        "onlooker": "inverse",
                        "mean_gap_percent": gap(float(np.mean(values)), best),
                        "best_gap_percent": gap(min(values), best),
                        "optimum_hits": sum(v <= best + 1e-6 for v in values),
                        "runs": runs,
                    }
                )
    return rows


def choose_parameters(rows):
    """Lowest average gap across development p values; ties go to the first grid position."""
    scores = {}
    for row in rows:
        scores.setdefault((row["foods"], row["limit_rule"]), []).append(row["mean_gap_percent"])
    (foods, rule), _ = min(scores.items(), key=lambda item: float(np.mean(item[1])))
    return foods, rule


def ablation(problem, ps, budget, runs, foods, rule):
    rows = []
    variants = {
        "wybrane ABC": {"peer_probability": 0.5, "onlooker": "inverse"},
        "bez inspiracji innym źródłem": {"peer_probability": 0.0, "onlooker": "inverse"},
        "obserwatorki rangowe": {"peer_probability": 0.5, "onlooker": "rank"},
        "bez obserwatorek": {"peer_probability": 0.5, "onlooker": "none"},
    }
    for p in ps:
        best = optimal(problem, p).objective
        for name, options in variants.items():
            values = [
                solve(
                    problem,
                    "abc",
                    p,
                    budget,
                    seed,
                    foods=foods,
                    limit=limit_value(rule, foods, p),
                    **options,
                ).objective
                for seed in range(runs)
            ]
            rows.append(
                {
                    "p": p,
                    "variant": name,
                    "mean_gap_percent": gap(float(np.mean(values)), best),
                    "optimum_hits": sum(v <= best + 1e-6 for v in values),
                    "runs": runs,
                }
            )
        if budget < greedy_construction_cost(len(problem.candidate_ids), p):
            continue
        reference = solve(problem, "greedy", p, budget).objective
        rows.append(
            {
                "p": p,
                "variant": "greedy + zamiany (deterministyczne)",
                "mean_gap_percent": gap(reference, best),
                "optimum_hits": int(reference <= best + 1e-6),
                "runs": 1,
            }
        )
    return rows


def compare(problem, ps, budget, runs, foods, rule, threshold=250):
    """E1: same budget for every heuristic, proved optimum as the reference."""
    rows, summary, histories = [], [], {}
    for p in ps:
        reference = optimal(problem, p)
        runs_by_method = {"abc": [], "random": [], "greedy": []}
        for method in runs_by_method:
            seeds = range(runs) if method != "greedy" else [0]
            for seed in seeds:
                try:
                    result = solve(
                        problem,
                        method,
                        p,
                        budget,
                        seed,
                        foods=foods,
                        limit=limit_value(rule, foods, p),
                    )
                except ValueError:
                    continue  # Greedy construction alone can exceed a very small budget.
                runs_by_method[method].append(result)
                histories.setdefault((p, method), []).append(result.history)
                rows.append(
                    {
                        "p": p,
                        "method": method,
                        "seed": seed if method != "greedy" else "",
                        "evaluations": result.evaluations,
                        "elapsed_s": result.elapsed_s,
                        **problem.metrics(result.selection, "aggregate", threshold),
                        "candidate_ids": ";".join(
                            problem.candidate_ids[i] for i in result.selection
                        ),
                    }
                )
        for method, results in runs_by_method.items():
            if not results:
                continue
            values = [r.objective for r in results]
            summary.append(
                {
                    "p": p,
                    "method": method,
                    "runs": len(results),
                    **summarize(values),
                    "optimum_m": reference.objective,
                    "mean_gap_percent": gap(float(np.mean(values)), reference.objective),
                    "optimum_hits": sum(v <= reference.objective + 1e-6 for v in values),
                    "mean_elapsed_s": float(np.mean([r.elapsed_s for r in results])),
                    "mean_evaluations": float(np.mean([r.evaluations for r in results])),
                }
            )
    tests = []
    for p in ps:
        by_method = {
            method: [r["mean_distance_m"] for r in rows if r["p"] == p and r["method"] == method]
            for method in ("abc", "random", "greedy")
        }
        tests.append(
            {
                "p": p,
                "question": "ABC vs losowanie, jednostronnie (Mann-Whitney)",
                "p_value": float(
                    mannwhitneyu(by_method["abc"], by_method["random"], alternative="less").pvalue
                ),
                "abc_runs_at_least_as_good_as_greedy": (
                    sum(v <= by_method["greedy"][0] + 1e-6 for v in by_method["abc"])
                    if by_method["greedy"]
                    else None
                ),
                "abc_runs": len(by_method["abc"]),
            }
        )
    for test, adjusted in zip(tests, holm([t["p_value"] for t in tests]), strict=True):
        test["holm_p_value"] = adjusted
    return rows, summary, tests, histories


def station_curve(problem, p_max, threshold=250):
    """E2: what one more station is worth."""
    rows, previous = [], None
    for p in range(1, p_max + 1):
        result = optimal(problem, p)
        metrics = problem.metrics(result.selection, "aggregate", threshold)
        rows.append(
            {
                "p": p,
                **metrics,
                "gain_vs_previous_m": None
                if previous is None
                else previous - metrics["mean_distance_m"],
                "candidate_ids": ";".join(problem.candidate_ids[i] for i in result.selection),
            }
        )
        previous = metrics["mean_distance_m"]
    return rows


def scenario_regret(problem, ps, threshold=250):
    """E3: one fixed aggregate layout against a layout optimized separately for each time of day."""
    rows = []
    for p in ps:
        fixed = optimal(problem, p).selection
        for scenario in problem.scenarios:
            own = optimal(problem, p, scenario)
            value = problem.objective(fixed, scenario)
            rows.append(
                {
                    "p": p,
                    "scenario": scenario,
                    "fixed_layout_m": value,
                    "scenario_optimum_m": own.objective,
                    "regret_percent": gap(value, own.objective),
                    "fixed_coverage": problem.metrics(fixed, scenario, threshold)["coverage"],
                    "common_stations": len(set(fixed) & set(own.selection)),
                }
            )
    return rows


def threshold_sensitivity(problem, ps):
    """E4: same layout, different definition of “close enough”."""
    rows = []
    for p in ps:
        fixed = optimal(problem, p).selection
        for threshold in THRESHOLDS:
            rows.append(
                {
                    "p": p,
                    "threshold_m": threshold,
                    "coverage": problem.metrics(fixed, "aggregate", threshold)["coverage"],
                }
            )
    return rows


def weight_variants(raw):
    """E5: every way of changing the assumed weights that the protocol asks about."""
    demand = raw["demand"]
    categories = sorted({d["category"] for d in demand if "category" in d})
    variants = {"jednolite": {name: [1.0] * len(demand) for name in raw["scenarios"]}}
    for category in categories:
        for factor, label in ((1.25, "+25%"), (0.75, "-25%")):
            variants[f"{category} {label}"] = {
                name: [
                    w * (factor if demand[i].get("category") == category else 1)
                    for i, w in enumerate(weights)
                ]
                for name, weights in raw["scenarios"].items()
            }
    if "category_weights" in raw:  # Floor area already splits each category; undo that choice.
        size = Counter(d["category"] for d in demand)
        variants["równo w kategorii"] = {
            name: [
                raw["category_weights"][d["category"]][name] / size[d["category"]] for d in demand
            ]
            for name in raw["scenarios"]
        }
    elif all("area_m2" in d for d in demand):
        mean_area = float(np.mean([d["area_m2"] for d in demand]))
        variants["skalowane powierzchnią"] = {
            name: [w * demand[i]["area_m2"] / mean_area for i, w in enumerate(weights)]
            for name, weights in raw["scenarios"].items()
        }
    return variants


def weight_sensitivity(problem, raw, ps):
    """E5: re-optimize under changed weights and measure what the base layout would lose."""
    rows, layouts = [], []
    for p in ps:
        base = optimal(problem, p).selection
        for name, scenarios in weight_variants(raw).items():
            changed = Problem(
                problem.candidate_ids,
                problem.demand_ids,
                problem.distances,
                {k: np.asarray(v) for k, v in scenarios.items()},
                dict(raw["scenario_mixture"]),
            )
            result = optimal(changed, p)
            layouts.append(result.selection)
            value = changed.objective(base)
            rows.append(
                {
                    "p": p,
                    "variant": name,
                    "base_layout_m": value,
                    "variant_optimum_m": result.objective,
                    "regret_percent": gap(value, result.objective),
                    "common_stations": len(set(base) & set(result.selection)),
                }
            )
    return rows, layouts


def field_priority(problem, raw, curve, layouts, ps):
    """Which candidates decide the results: the shortest useful list for the field audit."""
    counts = Counter()
    for row in curve:
        counts.update(row["candidate_ids"].split(";"))
    for selection in layouts:
        counts.update(problem.candidate_ids[i] for i in selection)
    for p in ps:
        for scenario in problem.scenarios:
            counts.update(problem.candidate_ids[i] for i in optimal(problem, p, scenario).selection)
    points = {c["id"]: c for c in raw["candidates"]}
    return [
        {
            "priority": rank,
            "id": identifier,
            "appearances_in_optimal_layouts": count,
            "lat": points[identifier]["lat"],
            "lon": points[identifier]["lon"],
            "source": points[identifier].get("source", ""),
            "status": points[identifier].get("status", ""),
        }
        for rank, (identifier, count) in enumerate(counts.most_common(), start=1)
    ]


def figures(output, summary, histories, curve, budget):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"abc": "#1654b8", "random": "#e78a27", "greedy": "#37864f"}
    labels = {"abc": "ABC", "random": "Losowanie", "greedy": "Greedy + zamiany"}
    ps = sorted({row["p"] for row in summary})
    fig, axes = plt.subplots(1, len(ps), figsize=(4.4 * len(ps), 4), squeeze=False)
    grid = np.arange(1, budget + 1)
    for ax, p in zip(axes[0], ps, strict=True):
        optimum = next(row["optimum_m"] for row in summary if row["p"] == p)
        for method, color in colors.items():
            curves = []
            for history in histories.get((p, method), []):
                evaluations = np.array([h[0] for h in history])
                values = np.array([h[1] for h in history])
                positions = np.searchsorted(evaluations, grid, side="right") - 1
                line = values[np.maximum(positions, 0)].astype(float)
                line[positions < 0] = np.nan
                curves.append(line)
            if not curves:
                continue
            curves = np.asarray(curves)
            valid = np.isfinite(curves).all(axis=0)
            ax.plot(
                grid[valid],
                100 * (np.median(curves[:, valid], axis=0) - optimum) / optimum,
                color=color,
                label=labels[method],
            )
            if len(curves) > 1:
                low, high = np.quantile(curves[:, valid], [0.25, 0.75], axis=0)
                ax.fill_between(
                    grid[valid],
                    100 * (low - optimum) / optimum,
                    100 * (high - optimum) / optimum,
                    color=color,
                    alpha=0.15,
                )
        ax.set_title(f"p = {p}")
        ax.set_xscale("log")
        ax.set_xlabel("Liczba ocen funkcji celu")
        ax.grid(alpha=0.25)
    axes[0][0].set_ylabel("Strata do optimum [%]")
    axes[0][-1].legend()
    fig.tight_layout()
    fig.savefig(output / "convergence.png", dpi=160)
    plt.close(fig)

    fig, left = plt.subplots(figsize=(7, 4))
    p_values = [row["p"] for row in curve]
    left.plot(p_values, [row["mean_distance_m"] for row in curve], "o-", color="#1654b8")
    left.set(xlabel="Liczba stacji p", ylabel="Średnie ważone dojście [m]")
    right = left.twinx()
    right.plot(p_values, [100 * row["coverage"] for row in curve], "s--", color="#e78a27")
    right.set_ylabel("Popyt w zasięgu 250 m [%]")
    left.grid(alpha=0.25)
    left.set_title("Korzyść z kolejnych stacji (układy optymalne)")
    fig.tight_layout()
    fig.savefig(output / "stations_curve.png", dpi=160)
    plt.close(fig)


def layout_map(output, map_path, raw, curve, p):
    """The proved-optimal layout for the middle p, with every candidate and demand point."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection

    features = json.loads(Path(map_path).read_text(encoding="utf-8"))["features"]
    walks = [f["geometry"]["coordinates"] for f in features if f["properties"]["kind"] == "walk"]
    outlines = []
    for feature in features:
        if feature["properties"]["kind"] != "building":
            continue
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        outlines.extend(np.asarray(polygon[0])[:, :2] for polygon in polygons)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.add_collection(PolyCollection(outlines, facecolors="#e0e5ed", edgecolors="#c3cad3", lw=0.3))
    ax.add_collection(LineCollection(walks, colors="#b3bac2", linewidths=0.35, zorder=1))
    selected = set(next(r for r in curve if r["p"] == p)["candidate_ids"].split(";"))
    candidates, demand = raw["candidates"], raw["demand"]
    ax.scatter(
        [c["lon"] for c in candidates],
        [c["lat"] for c in candidates],
        c="#6b7280",
        marker=".",
        s=30,
        label="Kandydaci (wymagają audytu)",
        zorder=3,
    )
    ax.scatter(
        [d["lon"] for d in demand],
        [d["lat"] for d in demand],
        c="#e78a27",
        marker="^",
        s=28,
        label="Punkty popytu (wagi założone)",
        zorder=3,
    )
    chosen = [c for c in candidates if c["id"] in selected]
    ax.scatter(
        [c["lon"] for c in chosen],
        [c["lat"] for c in chosen],
        c="#1654b8",
        s=130,
        label=f"Układ optymalny, p = {p}",
        zorder=4,
    )
    for point in chosen:
        ax.annotate(
            point["id"].removeprefix("candidate-"),
            (point["lon"], point["lat"]),
            xytext=(7, 7),
            textcoords="offset points",
            color="#1654b8",
        )
    ax.set_xlim(
        min(c["lon"] for c in candidates) - 0.002, max(c["lon"] for c in candidates) + 0.002
    )
    ax.set_ylim(
        min(c["lat"] for c in candidates) - 0.002, max(c["lat"] for c in candidates) + 0.002
    )
    ax.set_aspect(1 / np.cos(np.radians(np.mean([c["lat"] for c in candidates]))))
    ax.set(xlabel="Długość geograficzna [°]", ylabel="Szerokość geograficzna [°]")
    ax.legend(loc="upper right", fontsize=8)
    fig.text(
        0.5, 0.01, "© OpenStreetMap contributors | ODbL | wersja robocza, bez audytu", ha="center"
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output / "layout_map.png", dpi=160)
    plt.close(fig)


def run(
    problem_path,
    development_path,
    output,
    ps=(3, 5, 8),
    budget=10_000,
    runs=30,
    tuning_runs=10,
    p_max=15,
):
    problem_path, output = Path(problem_path), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    problem = Problem.load(problem_path)
    raw = json.loads(problem_path.read_text(encoding="utf-8"))
    development = Problem.load(development_path)
    development_ps = (5, 10, 20)

    grid = tune(development, development_ps, budget, tuning_runs)
    write_rows(output / "abc_tuning.csv", grid)
    foods, rule = choose_parameters(grid)
    print(f"Chosen on the development instance: foods={foods}, limit={rule}", flush=True)
    write_rows(
        output / "abc_ablation.csv",
        ablation(development, development_ps, budget, tuning_runs, foods, rule),
    )

    rows, summary, tests, histories = compare(problem, ps, budget, runs, foods, rule)
    write_rows(output / "runs.csv", rows)
    write_rows(output / "comparison.csv", summary)
    write_rows(output / "tests.csv", tests)
    curve = station_curve(problem, min(p_max, len(problem.candidate_ids)))
    write_rows(output / "stations_curve.csv", curve)
    write_rows(output / "scenarios.csv", scenario_regret(problem, ps))
    write_rows(output / "thresholds.csv", threshold_sensitivity(problem, ps))
    weights, layouts = weight_sensitivity(problem, raw, ps)
    write_rows(output / "weights.csv", weights)
    write_rows(output / "candidates_to_check.csv", field_priority(problem, raw, curve, layouts, ps))
    figures(output, summary, histories, curve, budget)
    if (problem_path.parent / "map.geojson").exists():
        layout_map(output, problem_path.parent / "map.geojson", raw, curve, ps[len(ps) // 2])
    reviewed = sum(c.get("status") == "reviewed" for c in raw["candidates"])
    write_json(
        output / "study.json",
        {
            "dataset_id": raw.get("dataset_id"),
            "problem_sha256": hashlib.sha256(problem_path.read_bytes()).hexdigest(),
            "development_sha256": hashlib.sha256(Path(development_path).read_bytes()).hexdigest(),
            "parameters": {
                "ps": list(ps),
                "budget": budget,
                "runs": runs,
                "tuning_runs": tuning_runs,
                "chosen_foods": foods,
                "chosen_limit_rule": rule,
            },
            "candidates": len(raw["candidates"]),
            "candidates_reviewed": reviewed,
            "demand_points": len(raw["demand"]),
            "draft": reviewed < len(raw["candidates"]),
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": scipy_version,
            },
            "rng": "numpy.random.default_rng (PCG64), seeds 0..runs-1",
        },
    )
    return summary
