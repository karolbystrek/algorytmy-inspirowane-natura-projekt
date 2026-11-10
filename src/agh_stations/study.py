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
from agh_stations.model import Problem, weighted_quantile
from agh_stations.routing import read_walk_edges, walking_matrix
from agh_stations.solvers import greedy_construction_cost, optimal, robust_optimal, solve

THRESHOLDS = (150, 250, 350)
FOODS = (8, 12, 24)
LIMIT_RULES = ("15", "30", "60", "foods*p")
GA_POPULATIONS = (20, 50, 100)
GA_MUTATIONS = (0.1, 0.4)
GA_CROSSOVERS = ("union", "greedy")
DEFAULT_GA = {"population": 100, "mutation": 0.4, "crossover": "union"}  # Tuned result.


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


def tune_ga(problem, ps, budget, runs):
    """The same search effort as ABC gets: 12 settings on the development instance."""
    rows = []
    for p in ps:
        best = optimal(problem, p).objective
        for population in GA_POPULATIONS:
            for mutation in GA_MUTATIONS:
                for crossover in GA_CROSSOVERS:
                    values = [
                        solve(
                            problem,
                            "ga",
                            p,
                            budget,
                            seed,
                            population=population,
                            mutation=mutation,
                            crossover=crossover,
                        ).objective
                        for seed in range(runs)
                    ]
                    rows.append(
                        {
                            "p": p,
                            "population": population,
                            "mutation": mutation,
                            "crossover": crossover,
                            "mean_gap_percent": gap(float(np.mean(values)), best),
                            "best_gap_percent": gap(min(values), best),
                            "optimum_hits": sum(v <= best + 1e-6 for v in values),
                            "runs": runs,
                        }
                    )
    return rows


def choose_ga_parameters(rows):
    """Lowest average gap across development p values; ties go to the first grid position."""
    scores = {}
    for row in rows:
        key = (row["population"], row["mutation"], row["crossover"])
        scores.setdefault(key, []).append(row["mean_gap_percent"])
    (population, mutation, crossover), _ = min(
        scores.items(), key=lambda item: float(np.mean(item[1]))
    )
    return {"population": population, "mutation": mutation, "crossover": crossover}


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


def compare(problem, ps, budget, runs, foods, rule, threshold=250, ga=None):
    """E1: same budget for every heuristic, proved optimum as the reference."""
    rows, summary, histories = [], [], {}
    ga = ga or DEFAULT_GA
    for p in ps:
        reference = optimal(problem, p)
        runs_by_method = {"abc": [], "ga": [], "random": [], "greedy": []}
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
                        **ga,
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


def ga_against_abc(rows, ps):
    """E1: do the two swarm-and-evolution methods differ? Two-sided, fixed before the runs."""
    tests = []
    for p in ps:
        abc, ga = (
            [r["mean_distance_m"] for r in rows if r["p"] == p and r["method"] == method]
            for method in ("abc", "ga")
        )
        tests.append(
            {
                "p": p,
                "question": "GA vs ABC, dwustronnie (Mann-Whitney)",
                "abc_mean_m": float(np.mean(abc)),
                "ga_mean_m": float(np.mean(ga)),
                "p_value": float(mannwhitneyu(abc, ga).pvalue) if len({*abc, *ga}) > 1 else 1.0,
            }
        )
    for test, adjusted in zip(tests, holm([t["p_value"] for t in tests]), strict=True):
        test["holm_p_value"] = adjusted
    return tests


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


def robust_layouts(problem, ps):
    """E3: can one layout share the loss between times of day, and what does that cost?"""
    rows = []
    for p in ps:
        fixed = optimal(problem, p).selection
        result = robust_optimal(problem, p)
        own = {name: optimal(problem, p, name).objective for name in problem.scenarios}
        rows.append(
            {
                "p": p,
                "aggregate_layout_worst_regret_percent": max(
                    gap(problem.objective(fixed, name), value) for name, value in own.items()
                ),
                "robust_layout_worst_regret_percent": result["worst_regret_percent"],
                "robust_cost_on_aggregate_percent": gap(
                    problem.objective(result["selection"]), problem.objective(fixed)
                ),
                "common_stations": len(set(fixed) & set(result["selection"])),
                "proved_optimal": result["proved"],
                "candidate_ids": ";".join(problem.candidate_ids[i] for i in result["selection"]),
            }
        )
    return rows


def large_station_counts(problem, ps, budgets, runs, foods, rule, ga=None):
    """E1b: larger p, and whether greedy still fits in the budget that ABC is given."""
    rows = []
    ga = ga or DEFAULT_GA
    m = len(problem.candidate_ids)
    for budget, repeats in budgets:
        for p in (p for p in ps if p < m):
            optimum = optimal(problem, p).objective
            limit = limit_value(rule, foods, p)
            abc = [
                solve(problem, "abc", p, budget, s, foods=foods, limit=limit).objective
                for s in range(repeats)
            ]
            genetic = [solve(problem, "ga", p, budget, s, **ga).objective for s in range(repeats)]
            random = [solve(problem, "random", p, budget, s).objective for s in range(repeats)]
            greedy = (
                solve(problem, "greedy", p, budget)
                if budget >= greedy_construction_cost(m, p)
                else None
            )
            rows.append(
                {
                    "p": p,
                    "budget": budget,
                    "runs": repeats,
                    "optimum_m": optimum,
                    "abc_mean_gap_percent": gap(float(np.mean(abc)), optimum),
                    "abc_best_gap_percent": gap(min(abc), optimum),
                    "abc_optimum_hits": sum(v <= optimum + 1e-6 for v in abc),
                    "ga_mean_gap_percent": gap(float(np.mean(genetic)), optimum),
                    "ga_best_gap_percent": gap(min(genetic), optimum),
                    "ga_optimum_hits": sum(v <= optimum + 1e-6 for v in genetic),
                    "random_mean_gap_percent": gap(float(np.mean(random)), optimum),
                    "greedy_gap_percent": None
                    if greedy is None
                    else gap(greedy.objective, optimum),
                    "greedy_evaluations": None if greedy is None else greedy.evaluations,
                    "greedy_ran_out_of_budget": greedy is None or greedy.evaluations >= budget,
                    "abc_runs_at_least_as_good_as_greedy": None
                    if greedy is None
                    else sum(v <= greedy.objective + 1e-6 for v in abc),
                }
            )
    return rows


def multistart_comparison(problem, ps, budget, runs, foods, rule, ga=None):
    """E1c: greedy stops early, so compare ABC with a local search spending the same budget."""
    rows = []
    ga = ga or DEFAULT_GA
    for p in (p for p in ps if p < len(problem.candidate_ids)):
        optimum = optimal(problem, p).objective
        limit = limit_value(rule, foods, p)
        abc = [
            solve(problem, "abc", p, budget, s, foods=foods, limit=limit).objective
            for s in range(runs)
        ]
        restarts = [solve(problem, "multistart", p, budget, s).objective for s in range(runs)]
        genetic = [solve(problem, "ga", p, budget, s, **ga).objective for s in range(runs)]
        rows.append(
            {
                "p": p,
                "budget": budget,
                "runs": runs,
                "optimum_m": optimum,
                "abc_mean_gap_percent": gap(float(np.mean(abc)), optimum),
                "abc_optimum_hits": sum(v <= optimum + 1e-6 for v in abc),
                "multistart_mean_gap_percent": gap(float(np.mean(restarts)), optimum),
                "multistart_optimum_hits": sum(v <= optimum + 1e-6 for v in restarts),
                "ga_mean_gap_percent": gap(float(np.mean(genetic)), optimum),
                "ga_optimum_hits": sum(v <= optimum + 1e-6 for v in genetic),
                "two_sided_p_value": float(mannwhitneyu(abc, restarts).pvalue)
                if len({*abc, *restarts}) > 1
                else 1.0,
            }
        )
    return rows


def candidate_count_curve(problem, raw, ps, fractions=(0.15, 0.25, 0.5, 0.75), subsets=20, seed=7):
    """E4: how the optimum depends on the number of candidates, over random shorter lists."""
    rng = np.random.default_rng(seed)
    m = len(problem.candidate_ids)
    rows = []
    for p in ps:
        full = optimal(problem, p).objective
        for fraction in fractions:
            size = max(p, int(fraction * m))
            values = [
                optimal(
                    problem.restricted_to(sorted(int(j) for j in rng.permutation(m)[:size])), p
                ).objective
                for _ in range(subsets)
            ]
            rows.append(
                {
                    "p": p,
                    "candidates": size,
                    "subsets": subsets,
                    "mean_optimum_m": float(np.mean(values)),
                    "best_optimum_m": float(min(values)),
                    "worst_optimum_m": float(max(values)),
                    "mean_loss_vs_full_list_percent": gap(float(np.mean(values)), full),
                }
            )
    return rows


def choose_stages(curve, coverage_target=0.75, minimum_gain_m=5.0):
    """Stage 1: fewest stations reaching the coverage target. Stage 2: last station worth 5 m."""
    first = next((r["p"] for r in curve if r["coverage"] >= coverage_target), curve[-1]["p"])
    worthwhile = [
        r["p"]
        for r in curve
        if r["gain_vs_previous_m"] is not None and r["gain_vs_previous_m"] >= minimum_gain_m
    ]
    return first, max(first, max(worthwhile, default=first))


def recommendation(problem, raw, stage_one, stage_two, threshold=250):
    """A staged layout: build the first stations, then extend them without moving any."""
    first = optimal(problem, stage_one)
    extended = optimal(problem, stage_two, fixed=first.selection)
    free = optimal(problem, stage_two)
    weights = problem.weights()
    summary = []
    for name, result in (
        ("etap 1", first),
        ("etap 2 (rozbudowa etapu 1)", extended),
        ("optimum bez etapów", free),
    ):
        summary.append(
            {
                "layout": name,
                "p": len(result.selection),
                **problem.metrics(result.selection, "aggregate", threshold),
                "loss_vs_free_optimum_percent": gap(
                    result.objective, optimal(problem, len(result.selection)).objective
                ),
                "candidate_ids": ";".join(problem.candidate_ids[i] for i in result.selection),
            }
        )
    selected = list(extended.selection)
    routes = problem.distances[:, selected]
    assignment, nearest = routes.argmin(axis=1), routes.min(axis=1)
    stations = []
    for k, j in enumerate(selected):
        mask = assignment == k
        served = float(weights[mask].sum())
        largest = int(np.flatnonzero(mask)[weights[mask].argmax()]) if mask.any() else None
        candidate = raw["candidates"][j]
        stations.append(
            {
                "id": candidate["id"],
                "stage": 1 if j in first.selection else 2,
                "lat": candidate.get("lat"),
                "lon": candidate.get("lon"),
                "source": candidate.get("source", ""),
                "buildings": int(mask.sum()),
                "demand_share": served,
                "mean_m": float(weights[mask] @ nearest[mask] / served) if served else None,
                "max_m": float(nearest[mask].max()) if mask.any() else None,
                "largest_building": None
                if largest is None
                else raw["demand"][largest].get("name", raw["demand"][largest]["id"]),
            }
        )
    return summary, sorted(stations, key=lambda s: (s["stage"], -s["demand_share"]))


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


def floor_area_variants(raw):
    """E5: undo, one at a time, the assumptions behind weights based on floor area."""
    demand = raw["demand"]
    size = Counter(d["category"] for d in demand)
    equal, footprint, fixed = {}, {}, {}
    for name, weights in raw["scenarios"].items():
        total = Counter()
        area = Counter()
        for item, weight in zip(demand, weights, strict=True):
            total[item["category"]] += weight
            area[item["category"]] += item["floor_area_m2"]
        equal[name] = [total[d["category"]] / size[d["category"]] for d in demand]
        footprint[name] = [
            w * d["area_m2"] / d["floor_area_m2"] for w, d in zip(weights, demand, strict=True)
        ]
        if "fixed_category_totals_for_sensitivity" in raw:
            totals = raw["fixed_category_totals_for_sensitivity"]
            fixed[name] = [
                totals[d["category"]][name] * d["floor_area_m2"] / area[d["category"]]
                for d in demand
            ]
    variants = {"równo w kategorii": equal, "bez pięter (tylko obrys budynku)": footprint}
    if fixed:
        variants["stałe udziały kategorii (poprzednia reguła)"] = fixed
    return variants


def mixture_variants(raw):
    """E5: the aggregate treats each time of day as equally busy; count one of them twice."""
    if len(raw["scenarios"]) < 2:
        return {}
    return {
        f"mieszanina: {scenario} ×2": {
            name: value * (2 if name == scenario else 1)
            for name, value in raw["scenario_mixture"].items()
        }
        for scenario in raw["scenarios"]
    }


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
    if all("floor_area_m2" in d for d in demand):
        variants |= floor_area_variants(raw)
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
    changes = [(name, s, raw["scenario_mixture"]) for name, s in weight_variants(raw).items()]
    changes += [(name, raw["scenarios"], m) for name, m in mixture_variants(raw).items()]
    for p in ps:
        base = optimal(problem, p).selection
        for name, scenarios, mixture in changes:
            changed = Problem(
                problem.candidate_ids,
                problem.demand_ids,
                problem.distances,
                {k: np.asarray(v, dtype=float) for k, v in scenarios.items()},
                dict(mixture),
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


def group_metrics(problem, raw, ps, threshold=250):
    """E6: the mean can hide long walks and one badly served group of buildings."""
    weights = problem.weights()
    categories = sorted({d["category"] for d in raw["demand"] if "category" in d})
    rows = []
    for p in ps:
        nearest = problem.nearest(optimal(problem, p).selection)
        groups = {"wszystkie": np.ones(len(weights), dtype=bool)}
        for category in categories:
            groups[category] = np.array([d.get("category") == category for d in raw["demand"]])
        for name, mask in groups.items():
            share = weights[mask] / weights[mask].sum()
            rows.append(
                {
                    "p": p,
                    "group": name,
                    "buildings": int(mask.sum()),
                    "mean_m": float(share @ nearest[mask]),
                    "weighted_p90_m": weighted_quantile(nearest[mask], weights[mask]),
                    "max_m": float(nearest[mask].max()),
                    "coverage": float(share @ (nearest[mask] <= threshold)),
                }
            )
    return rows


def list_sensitivity(problem, raw, ps, threshold=250, seed=2026):
    """E4: does the answer depend on which points we chose to model?

    Subsets are nested, fixed by the seed and judged on the complete demand list, so a shorter
    list cannot look better merely because distant buildings were left out.
    """
    rng = np.random.default_rng(seed)
    n, m = problem.distances.shape
    order = rng.permutation(m)
    candidate_sets = {
        "3/4 kandydatów": sorted(int(j) for j in order[: 3 * m // 4]),
        "1/2 kandydatów": sorted(int(j) for j in order[: m // 2]),
        "1/4 kandydatów": sorted(int(j) for j in order[: m // 4]),
    }
    existing = [
        j for j, c in enumerate(raw["candidates"]) if str(c.get("source", "")).startswith("osm_")
    ]
    if existing and len(existing) < m:
        candidate_sets["tylko istniejące parkingi z OSM"] = existing
    half = []
    for category in sorted({d.get("category") for d in raw["demand"]}, key=str):
        members = [i for i, d in enumerate(raw["demand"]) if d.get("category") == category]
        chosen = rng.permutation(members)[: max(1, len(members) // 2)]
        half.extend(int(i) for i in chosen)
    demand_sets = {"połowa budynków w każdej kategorii": sorted(half)}
    without_other = [i for i, d in enumerate(raw["demand"]) if d.get("category") != "other"]
    if 0 < len(without_other) < n:
        demand_sets["bez kategorii other"] = without_other
    with_doors = [
        i for i, d in enumerate(raw["demand"]) if d.get("location_method") == "osm_entrances"
    ]
    if 0 < len(with_doors) < n:
        demand_sets["tylko budynki z wejściami w OSM"] = with_doors
    rows = []

    def describe(p, base, change, variant, points, selection):
        value = problem.objective(selection)
        return {
            "p": p,
            "change": change,
            "variant": variant,
            "points": points,
            "layout_on_full_demand_m": value,
            "loss_percent": gap(value, base.objective),
            "coverage": problem.metrics(selection, "aggregate", threshold)["coverage"],
            "common_stations": len(set(selection) & set(base.selection)),
        }

    for p in ps:
        base = optimal(problem, p)
        for name, indices in candidate_sets.items():
            if len(indices) < p:
                continue
            smaller = Problem(
                [problem.candidate_ids[j] for j in indices],
                problem.demand_ids,
                problem.distances[:, indices],
                {k: np.asarray(v, dtype=float) for k, v in raw["scenarios"].items()},
                dict(raw["scenario_mixture"]),
            )
            selection = tuple(indices[j] for j in optimal(smaller, p).selection)
            rows.append(describe(p, base, "kandydaci", name, len(indices), selection))
        for name, indices in demand_sets.items():
            smaller = Problem(
                problem.candidate_ids,
                [problem.demand_ids[i] for i in indices],
                problem.distances[indices, :],
                {k: np.asarray(v, dtype=float)[indices] for k, v in raw["scenarios"].items()},
                dict(raw["scenario_mixture"]),
            )
            selection = optimal(smaller, p).selection
            rows.append(describe(p, base, "popyt", name, len(indices), selection))
    return rows


def gate_sensitivity(problem, raw, ps):
    """E7: the same layout if every gate of unknown status turned out to be locked."""
    if "distances_m_gates_closed" not in raw:
        return []
    closed = np.array(
        [[np.nan if v is None else v for v in row] for row in raw["distances_m_gates_closed"]],
        dtype=float,
    )
    weights = problem.weights()
    rows = []
    for p in ps:
        selection = list(optimal(problem, p).selection)
        rows.append(
            {"p": p, **closed_gate_effect(closed, weights, problem.nearest(selection), selection)}
        )
    return rows


def closed_gate_effect(closed, weights, open_nearest, selection):
    """A layout's walk if every gate of unknown status were locked (NaN = no route)."""
    routes = closed[:, selection]
    reachable = ~np.isnan(routes).all(axis=1)
    if not reachable.any():
        return {
            "demand_without_route": float(weights.sum()),
            "buildings_without_route": len(weights),
            "mean_open_m": None,
            "mean_closed_m": None,
            "increase_percent": None,
        }
    nearest = np.nanmin(routes[reachable], axis=1)
    share = weights[reachable] / weights[reachable].sum()
    open_mean = float(share @ open_nearest[reachable])
    closed_mean = float(share @ nearest)
    return {
        "demand_without_route": float(weights[~reachable].sum()),
        "buildings_without_route": int((~reachable).sum()),
        "mean_open_m": open_mean,
        "mean_closed_m": closed_mean,
        "increase_percent": gap(closed_mean, open_mean),
    }


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

    colors = {"abc": "#0e7a5a", "ga": "#8a4fbf", "random": "#b67a1e", "greedy": "#4a7cc9"}
    labels = {"abc": "ABC", "ga": "GA", "random": "Losowanie", "greedy": "Greedy + zamiany"}
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

    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4), sharex=True)
    p_values = [row["p"] for row in curve]
    left.plot(p_values, [row["mean_distance_m"] for row in curve], "o-", ms=3, color="#1654b8")
    left.set(xlabel="Liczba stacji p", ylabel="Średnie ważone dojście [m]")
    right.plot(p_values, [100 * row["coverage"] for row in curve], "o-", ms=3, color="#1654b8")
    right.set(xlabel="Liczba stacji p", ylabel="Popyt w zasięgu 250 m [%]")
    left.grid(alpha=0.25)
    right.grid(alpha=0.25)
    fig.suptitle("Korzyść z kolejnych stacji (układy optymalne)")
    fig.tight_layout()
    fig.savefig(output / "stations_curve.png", dpi=160)
    plt.close(fig)


def large_p_figure(output, rows):
    """Loss to the optimum as p grows, at the tightest budget of the larger-p experiment."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    budget = min(row["budget"] for row in rows)
    chosen = [row for row in rows if row["budget"] == budget]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(
        [row["p"] for row in chosen],
        [row["abc_mean_gap_percent"] for row in chosen],
        "o-",
        color="#0e7a5a",
        label="ABC (średnia)",
    )
    ax.plot(
        [row["p"] for row in chosen],
        [row["ga_mean_gap_percent"] for row in chosen],
        "^-",
        color="#8a4fbf",
        label="GA (średnia)",
    )
    finished = [row for row in chosen if row["greedy_gap_percent"] is not None]
    ax.plot(
        [row["p"] for row in finished],
        [row["greedy_gap_percent"] for row in finished],
        "s--",
        color="#4a7cc9",
        label="Greedy + zamiany",
    )
    ax.set(
        xlabel="Liczba stacji p",
        ylabel="Strata do optimum [%]",
        title=f"Większa liczba stacji, budżet {budget} ocen",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "large_p.png", dpi=160)
    plt.close(fig)


def layout_map(output, map_path, raw, layers, filename="layout_map.png"):
    """Chosen layouts over every candidate and demand point; layers = (label, ids, color)."""
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
    for label, identifiers, color in layers:
        chosen = [c for c in candidates if c["id"] in identifiers]
        ax.scatter(
            [c["lon"] for c in chosen],
            [c["lat"] for c in chosen],
            c=color,
            s=130,
            label=label,
            zorder=4,
        )
        for point in chosen:
            ax.annotate(
                point["id"].removeprefix("candidate-"),
                (point["lon"], point["lat"]),
                xytext=(7, 7),
                textcoords="offset points",
                color=color,
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
        0.5, 0.01, "© OpenStreetMap contributors | ODbL | stan przed audytem terenowym", ha="center"
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output / filename, dpi=160)
    plt.close(fig)


def run(
    problem_path,
    development_path,
    output,
    ps=(3, 5, 8),
    budget=10_000,
    runs=30,
    tuning_runs=10,
    p_max=40,
    large_ps=(10, 15, 20, 25, 30, 40),
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
    ga_grid = tune_ga(development, development_ps, budget, tuning_runs)
    write_rows(output / "ga_tuning.csv", ga_grid)
    ga = choose_ga_parameters(ga_grid)
    print(f"Chosen on the development instance: {ga}", flush=True)
    write_rows(
        output / "abc_ablation.csv",
        ablation(development, development_ps, budget, tuning_runs, foods, rule),
    )

    rows, summary, tests, histories = compare(problem, ps, budget, runs, foods, rule, ga=ga)
    write_rows(output / "runs.csv", rows)
    write_rows(output / "comparison.csv", summary)
    write_rows(output / "tests.csv", tests)
    write_rows(output / "ga_tests.csv", ga_against_abc(rows, ps))
    curve = station_curve(problem, min(p_max, len(problem.candidate_ids)))
    write_rows(output / "stations_curve.csv", curve)
    large = large_station_counts(
        problem,
        large_ps,
        ((budget, runs), (3 * budget, max(1, runs // 3))),
        runs,
        foods,
        rule,
        ga,
    )
    if large:
        write_rows(output / "large_p.csv", large)
        large_p_figure(output, large)
    write_rows(output / "scenarios.csv", scenario_regret(problem, ps))
    write_rows(
        output / "multistart.csv",
        multistart_comparison(problem, sorted({*ps, *large_ps[:3]}), budget, runs, foods, rule, ga),
    )
    write_rows(output / "candidate_count.csv", candidate_count_curve(problem, raw, ps))
    stage_one, stage_two = choose_stages(curve)
    summary_rows, station_rows = recommendation(problem, raw, stage_one, stage_two)
    write_rows(output / "recommended_layouts.csv", summary_rows)
    write_rows(output / "recommended_stations.csv", station_rows)
    if len(problem.scenarios) > 1:
        write_rows(output / "robust.csv", robust_layouts(problem, sorted({*ps, *large_ps[:2]})))
    write_rows(output / "thresholds.csv", threshold_sensitivity(problem, ps))
    write_rows(output / "groups.csv", group_metrics(problem, raw, ps))
    write_rows(output / "point_lists.csv", list_sensitivity(problem, raw, ps))
    gates = gate_sensitivity(problem, raw, ps)
    if gates:
        write_rows(output / "gates.csv", gates)
    weights, layouts = weight_sensitivity(problem, raw, ps)
    write_rows(output / "weights.csv", weights)
    write_rows(output / "candidates_to_check.csv", field_priority(problem, raw, curve, layouts, ps))
    figures(output, summary, histories, curve, budget)
    if (problem_path.parent / "map.geojson").exists():
        p = ps[len(ps) // 2]
        identifiers = set(next(r for r in curve if r["p"] == p)["candidate_ids"].split(";"))
        layout_map(
            output,
            problem_path.parent / "map.geojson",
            raw,
            [(f"Układ optymalny, p = {p}", identifiers, "#1654b8")],
        )
        by_stage = {
            stage: {row["id"] for row in station_rows if row["stage"] == stage} for stage in (1, 2)
        }
        layout_map(
            output,
            problem_path.parent / "map.geojson",
            raw,
            [
                (f"Etap 1: {len(by_stage[1])} stacji", by_stage[1], "#1654b8"),
                (f"Etap 2: dodatkowe {len(by_stage[2])} stacji", by_stage[2], "#c2571f"),
            ],
            "layout_recommended.png",
        )
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
                "chosen_ga": ga,
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
