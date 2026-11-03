"""One-command, offline entrance-to-station demonstrator and review packet."""

import csv
import html
from argparse import Namespace
from pathlib import Path

import numpy as np

from agh_stations.cli import benchmark
from agh_stations.demo_data import prepare_dataset, read_json, sha256, write_json
from agh_stations.model import Problem


def export_routes(problem_data, graph, selection):
    import networkx as nx

    problem = Problem(
        [c["id"] for c in problem_data["candidates"]],
        [d["id"] for d in problem_data["demand"]],
        problem_data["distances_m"],
        dict(problem_data["scenarios"]),
        problem_data["scenario_mixture"],
    )
    features = []
    for i, demand in enumerate(problem_data["demand"]):
        column = min(selection, key=lambda j: (problem.distances[i, j], j))
        candidate = problem_data["candidates"][column]
        nodes = nx.shortest_path(graph, demand["node_id"], candidate["node_id"], weight="length_m")
        edges = []
        for u, v in zip(nodes, nodes[1:], strict=False):
            key, data = min(graph[u][v].items(), key=lambda item: (item[1]["length_m"], item[0]))
            edges.append(
                {
                    "u": u,
                    "v": v,
                    "key": key,
                    "length_m": data["length_m"],
                    "osm_way_id": data["osm_way_id"],
                }
            )
        length = sum(edge["length_m"] for edge in edges)
        if not np.isclose(length, problem.distances[i, column], atol=1e-8, rtol=1e-10):
            raise ValueError("Exported route length differs from the optimization matrix")
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[graph.nodes[n]["lon"], graph.nodes[n]["lat"]] for n in nodes],
                },
                "properties": {
                    "demand_id": demand["id"],
                    "demand_name": demand["name"],
                    "candidate_id": candidate["id"],
                    "length_m": length,
                    "node_ids": nodes,
                    "edges": edges,
                    "field_review": "pending",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def write_review(output, problem_data):
    rows = []
    for kind, points in (
        ("entrance", problem_data["demand"]),
        ("candidate", problem_data["candidates"]),
    ):
        for point in points:
            rows.append(
                {
                    "id": point["id"],
                    "kind": kind,
                    "name": point["name"],
                    "node_id": point["node_id"],
                    "lat": point["lat"],
                    "lon": point["lon"],
                    "source_url": point["source_url"],
                    "field_status": "pending",
                    "field_checked_at": "",
                    "field_note": "",
                }
            )
    with (output / "field-review-template.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(output, problem_data, results, routes):
    summary = results["summary"]
    lines = [
        "# AGH — demonstrator 5 wejść / 10 kandydatów / 3 stacje",
        "",
        "**Weryfikacja mapowa. Kontrola terenowa odroczona; wszystkie 15 miejsc oraz trasy "
        "wymagają potwierdzenia w terenie.** Wagi popytu są jednakowe i założone.",
        "",
        "![Mapa tras](map.png)",
        "",
        "| Metoda | Przebiegi | Średnie dojście [m] | Najlepszy wynik [m] | Oceny |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in ("abc", "greedy", "random", "exact"):
        row = summary[method]
        lines.append(
            f"| {method} | {row['runs']} | {row['mean_m']:.3f} | {row['best_m']:.3f} "
            f"| {row['min_evaluations']}–{row['max_evaluations']} |"
        )
    lines += [
        "",
        "Greedy obejmuje zamiany 1-swap. Pełny przegląd ma osobny budżet 120 kombinacji.",
        "To mała instancja kontrolna: zgodne wyniki metod potwierdzają działanie pipeline’u, "
        "a nie przewagę któregoś algorytmu.",
        "",
        "## Pięć tras najlepszego układu ABC",
        "",
        "| Wejście | Stacja | Długość [m] |",
        "|---|---|---:|",
    ]
    for feature in routes["features"]:
        p = feature["properties"]
        lines.append(
            f"| {p['demand_id']} — {p['demand_name']} | {p['candidate_id']} | {p['length_m']:.2f} |"
        )
    lines += [
        "",
        "Każda linia składa się z zapisanych krawędzi OSM; nie dodano łączników "
        "od środka budynku. Pełne sekwencje i długości są w `routes.geojson`.",
        "",
        "## Źródła i kontrola miejsc",
        "",
        "Wersja danych OSM pochodzi z 29.10.2026; identyfikatory i hashe są w "
        "`dataset/manifest.json`. Wykaz AGH potwierdza tożsamość akademików, "
        "a nie aktualną dostępność wejść.",
        "Model obejmuje zapisany wycinek sieci; przejścia poza nim nie są uwzględniane. "
        "Zadaszenia `building=roof` nie są traktowane jak pełne ściany budynku; "
        "zachowujemy tylko istniejące pod nimi ścieżki OSM.",
        "",
        "| Miejsce | Odnośnik do OSM | Uzasadnienie / status |",
        "|---|---|---|",
    ]
    for point in problem_data["demand"]:
        lines.append(
            f"| {point['id']} — {point['name']} | [wejście]({point['source_url']}) "
            "| `entrance=main`, węzeł na obrysie i w grafie; teren: do sprawdzenia |"
        )
    for point in problem_data["candidates"]:
        lines.append(
            f"| {point['id']} — {point['name']} | [węzeł]({point['source_url']}) "
            f"| {point['reason']} |"
        )
    lines += [
        "",
        "Do notowania sprawdzeń skopiuj `field-review-template.csv` poza katalog wyników; "
        "szablon jest odtwarzany przy każdym uruchomieniu. Puste pola nie są potwierdzeniem. "
        "To propozycje miejsc, bez potwierdzonej dostępności "
        "przestrzeni i zgody na stację.",
        "",
        "![Zbieżność](convergence.png)",
        "",
        "Dane © OpenStreetMap contributors, [ODbL 1.0]"
        "(https://opendatacommons.org/licenses/odbl/1-0/). "
        "[Informacja OSM](https://www.openstreetmap.org/copyright).",
        "",
    ]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    # A self-contained local report document: no scripts, remote tiles, CDN or server.
    table_rows = "".join(
        f"<tr><td>{html.escape(f['properties']['demand_name'])}</td>"
        f"<td>{html.escape(f['properties']['candidate_id'])}</td>"
        f"<td>{f['properties']['length_m']:.2f} m</td></tr>"
        for f in routes["features"]
    )
    report = f"""<!doctype html><html lang="pl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AGH — 5 wejść, 10 kandydatów, 3 stacje</title>
<style>body{{font:17px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#15243b}}
img{{width:100%;height:auto}}aside{{padding:1rem;background:#fff0cf;border-left:5px solid #d18b17}}
table{{border-collapse:collapse;width:100%}}
td,th{{padding:.6rem;text-align:left;border-bottom:1px solid #ddd}}
@media print{{body{{margin:0}}}}</style>
<h1>5 wejść · 10 kandydatów · 3 stacje</h1>
<aside>Sprawdzone źródła mapowe.
Potwierdzenie terenowe wszystkich miejsc i przejść pozostaje do wykonania.
Popyt jest założony, a lokalizacje stacji są propozycjami.</aside>
<img src="map.svg" alt="Pięć tras od wejść akademików do trzech wybranych stacji">
<h2>Trasy najlepszego układu ABC</h2><table><thead><tr><th>Wejście</th><th>Stacja</th>
<th>Długość</th></tr></thead><tbody>{table_rows}</tbody></table>
<p>ABC: średnia {summary["abc"]["mean_m"]:.3f} m;
greedy + 1-swap: {summary["greedy"]["best_m"]:.3f} m;
optimum małej instancji: {summary["exact"]["best_m"]:.3f} m.</p>
<p><a href="README.md">Pełny raport i źródła punktów</a> ·
<a href="field-review-template.csv">Szablon kontroli terenowej</a>
 · <a href="routes.geojson">Trasy GeoJSON</a></p>
<img src="convergence.svg" alt="Porównanie zbieżności algorytmów">
<p>Dane © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>,
<a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL 1.0</a>.
Snapshot z 29.10.2026.</p></html>"""
    (output / "report.html").write_text(report, encoding="utf-8")


def run_demo(config_path, output_path, runs=None, budget=None):
    from agh_stations.report import render

    config = read_json(config_path)
    output = Path(output_path)
    problem_data, graph, manifest = prepare_dataset(config_path, output / "dataset")
    if config["p"] != 3:
        raise ValueError("This demonstrator selects exactly 3 stations")
    benchmark(
        Namespace(
            problem=str(output / "dataset/problem.json"),
            output=str(output),
            p=3,
            budget=budget if budget is not None else config["budget"],
            runs=runs if runs is not None else config["runs"],
            scenario="aggregate",
            threshold=250,
            foods=12,
            limit=30,
            exact=True,
        )
    )
    results = read_json(output / "results.json")
    routes = export_routes(problem_data, graph, results["best_solutions"]["abc"]["selection"])
    routes.update(
        problem_sha256=results["problem_sha256"],
        method="abc",
        candidate_ids=results["best_solutions"]["abc"]["candidate_ids"],
    )
    write_json(output / "routes.geojson", routes)
    write_review(output, problem_data)
    render(output, output / "dataset")
    write_report(output, problem_data, results, routes)
    write_json(
        output / "verification.json",
        {
            "dataset_id": config["dataset_id"],
            "source_sha256": manifest["source_sha256"],
            "problem_sha256": results["problem_sha256"],
            "routes_sha256": sha256(output / "routes.geojson"),
            "counts": {"entrances": 5, "candidates": 10, "selected_stations": 3, "routes": 5},
            "route_lengths_match_matrix": True,
            "all_pairs_reachable": True,
            "field_review": "pending — deferred by user",
            "offline_inputs": True,
        },
    )
    print(f"Report: {(output / 'report.html').resolve()}")
    return results
