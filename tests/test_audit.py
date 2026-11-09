"""The audit step may only remove points a person rejected, and must re-hash what it writes."""

import csv
import json

import pytest

from agh_stations.audit import apply, digest, write_template
from agh_stations.model import Problem


@pytest.fixture
def dataset(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    problem = {
        "schema_version": 1,
        "dataset_id": "x",
        "candidates": [
            {"id": "a", "lat": 1, "lon": 2},
            {"id": "b", "lat": 1, "lon": 3},
            {"id": "c", "lat": 1, "lon": 4},
        ],
        "demand": [
            {"id": "d1", "name": "Wydział", "lat": 2, "lon": 2},
            {"id": "d2", "name": "Hala", "lat": 2, "lon": 3},
        ],
        "distances_m": [[1, 2, 3], [4, 5, 6]],
        "scenarios": {"s": [1, 3]},
        "scenario_mixture": {"s": 1},
    }
    (source / "problem.json").write_text(json.dumps(problem), encoding="utf-8")
    (source / "map.geojson").write_text("{}", encoding="utf-8")
    manifest = {"dataset_id": "x", "files_sha256": {}, "quality": {}}
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return source


def edit(sheet, changes):
    with sheet.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(changes.get(row["id"], {}))
    with sheet.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


CHECKED = {"reviewer": "Osoba", "review_date": "2026-11-12"}


def test_template_keeps_names_and_refuses_to_overwrite_field_work(dataset, tmp_path):
    sheet = write_template(dataset, tmp_path / "audit.csv")
    assert "Wydział" in sheet.read_text(encoding="utf-8-sig")
    with pytest.raises(ValueError, match="already exists"):
        write_template(dataset, sheet)


def test_rejection_removes_the_matching_row_and_column(dataset, tmp_path):
    sheet = write_template(dataset, tmp_path / "audit.csv")
    edit(
        sheet,
        {
            "b": {"status": "rejected", "reason": "ogrodzenie", **CHECKED},
            "d1": {"status": "rejected", "reason": "brak wejścia", **CHECKED},
            "a": {"status": "reviewed", **CHECKED},
        },
    )
    output = tmp_path / "out"
    quality = apply(dataset, sheet, output)
    result = json.loads((output / "problem.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in result["candidates"]] == ["a", "c"]
    assert [p["id"] for p in result["demand"]] == ["d2"]
    assert result["distances_m"] == [[4, 6]]
    assert result["scenarios"] == {"s": [3]}
    assert quality["candidate_rejected"] == 1
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files_sha256"]["problem.json"] == digest(output / "problem.json")
    assert manifest["quality"]["reviewed_candidate_count"] == 1
    Problem.load(output / "problem.json")


def test_strict_mode_keeps_only_reviewed_points(dataset, tmp_path):
    sheet = write_template(dataset, tmp_path / "audit.csv")
    edit(sheet, {i: {"status": "reviewed", **CHECKED} for i in ("a", "d1", "d2")})
    apply(dataset, sheet, tmp_path / "out", strict=True)
    result = json.loads((tmp_path / "out" / "problem.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in result["candidates"]] == ["a"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"a": {"status": "maybe"}}, "unknown status"),
        ({"a": {"status": "reviewed", "review_date": "2026-11-12"}}, "reviewer"),
        ({"a": {"status": "reviewed", "reviewer": "O", "review_date": "dziś"}}, "YYYY-MM-DD"),
        ({"a": {"status": "rejected", **CHECKED}}, "reason"),
    ],
)
def test_incomplete_field_records_are_refused(dataset, tmp_path, changes, message):
    sheet = write_template(dataset, tmp_path / "audit.csv")
    edit(sheet, changes)
    with pytest.raises(ValueError, match=message):
        apply(dataset, sheet, tmp_path / "out")


def test_sheet_must_cover_the_dataset_and_output_must_differ(dataset, tmp_path):
    sheet = write_template(dataset, tmp_path / "audit.csv")
    with pytest.raises(ValueError, match="must differ"):
        apply(dataset, sheet, dataset)
    lines = sheet.read_text(encoding="utf-8-sig").splitlines()
    sheet.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="does not match"):
        apply(dataset, sheet, tmp_path / "out")
