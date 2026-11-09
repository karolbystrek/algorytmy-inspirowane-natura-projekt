"""Field-audit workflow: a spreadsheet of points and a filtered, re-hashed dataset built from it.

Only people who checked a place on site may mark it ``reviewed`` or ``rejected``; the code never
changes a status on its own. No network or geo dependency is needed here.
"""

import csv
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np

COLUMNS = [
    "type",
    "id",
    "name",
    "lat",
    "lon",
    "osm_link",
    "source",
    "status",
    "reason",
    "reviewer",
    "review_date",
    "evidence",
]
STATUSES = {"requires_review", "reviewed", "rejected"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_lf(path, text):
    """Always LF: .gitattributes normalizes checkouts, and hashes must survive that."""
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def write_json(path, value):
    write_lf(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _load(dataset_dir):
    return json.loads((Path(dataset_dir) / "problem.json").read_text(encoding="utf-8"))


def write_template(dataset_dir, audit_csv):
    """Create the sheet; refuses to overwrite because it may hold field observations."""
    audit_csv = Path(audit_csv)
    if audit_csv.exists():
        raise ValueError(f"{audit_csv} already exists; it may contain field work")
    problem = _load(dataset_dir)
    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig lets Excel on Windows open Polish names correctly.
    with audit_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        for kind, key in (("candidate", "candidates"), ("demand", "demand")):
            for point in problem[key]:
                writer.writerow(
                    {
                        "type": kind,
                        "id": point["id"],
                        "name": point.get("name", ""),
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "osm_link": (
                            "https://www.openstreetmap.org/"
                            f"?mlat={point['lat']}&mlon={point['lon']}#map=19/"
                            f"{point['lat']}/{point['lon']}"
                        ),
                        "source": point.get("source", point.get("location_method", "")),
                        "status": "requires_review",
                    }
                )
    return audit_csv


def _read_audit(audit_csv, problem):
    with Path(audit_csv).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    entries = {}
    for number, row in enumerate(rows, start=2):
        key = (row["type"], row["id"])
        if key in entries:
            raise ValueError(f"Line {number}: duplicate entry for {key}")
        if row["status"] not in STATUSES:
            raise ValueError(f"Line {number}: unknown status {row['status']!r}")
        if row["status"] != "requires_review":
            if not row["reviewer"].strip():
                raise ValueError(f"Line {number}: {row['status']} needs a reviewer")
            try:
                date.fromisoformat(row["review_date"])
            except ValueError as error:
                raise ValueError(f"Line {number}: review_date must be YYYY-MM-DD") from error
        if row["status"] == "rejected" and not row["reason"].strip():
            raise ValueError(f"Line {number}: rejected point needs a reason")
        entries[key] = row
    expected = {("candidate", p["id"]) for p in problem["candidates"]} | {
        ("demand", p["id"]) for p in problem["demand"]
    }
    if set(entries) != expected:
        missing, unknown = sorted(expected - set(entries)), sorted(set(entries) - expected)
        raise ValueError(f"Audit does not match dataset; missing={missing} unknown={unknown}")
    return entries


def apply(input_dir, audit_csv, output_dir, strict=False):
    """Drop rejected points (and, when strict, everything not yet reviewed) and re-hash."""
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("Output must differ from input; the source snapshot stays frozen")
    problem = _load(input_dir)
    entries = _read_audit(audit_csv, problem)
    allowed = {"reviewed"} if strict else {"reviewed", "requires_review"}

    def keep(kind, key):
        indices = []
        for index, point in enumerate(problem[key]):
            entry = entries[(kind, point["id"])]
            point["status"] = entry["status"]
            if entry["status"] != "requires_review":
                point["audit"] = {
                    field: entry[field]
                    for field in ("reason", "reviewer", "review_date", "evidence")
                }
            if entry["status"] in allowed:
                indices.append(index)
        return indices

    candidate_indices, demand_indices = keep("candidate", "candidates"), keep("demand", "demand")
    if not candidate_indices or not demand_indices:
        raise ValueError("Audit leaves no candidates or no demand points")
    quality = {
        f"{name}_{status}": sum(point["status"] == status for point in problem[key])
        for name, key in (("candidate", "candidates"), ("demand", "demand"))
        for status in sorted(STATUSES)
    }
    problem["candidates"] = [problem["candidates"][i] for i in candidate_indices]
    problem["demand"] = [problem["demand"][i] for i in demand_indices]
    problem["distances_m"] = (
        np.asarray(problem["distances_m"])[np.ix_(demand_indices, candidate_indices)]
    ).tolist()
    problem["scenarios"] = {
        name: [weights[i] for i in demand_indices] for name, weights in problem["scenarios"].items()
    }
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    problem["dataset_id"] = manifest["dataset_id"] = (
        f"{manifest['dataset_id']}-{'reviewed' if strict else 'audited'}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "problem.json", problem)
    shutil.copyfile(input_dir / "map.geojson", output_dir / "map.geojson")
    manifest["files_sha256"] = {
        name: digest(output_dir / name) for name in ("problem.json", "map.geojson")
    }
    manifest["quality"].update(quality)
    manifest["quality"]["reviewed_candidate_count"] = quality["candidate_reviewed"]
    manifest["audit"] = {
        "source_dataset_sha256": digest(input_dir / "problem.json"),
        "audit_sha256": digest(audit_csv),
        "strict": strict,
    }
    write_json(output_dir / "manifest.json", manifest)
    return quality
