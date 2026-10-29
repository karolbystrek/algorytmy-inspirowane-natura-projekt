"""Create only missing project labels using gh; default is a dry run."""

import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", default="karolbystrek/algorytmy-inspirowane-natura-projekt")
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
definition = Path(__file__).resolve().parents[1] / ".github/labels.json"
labels = json.loads(definition.read_text())
current = json.loads(
    subprocess.check_output(
        ["gh", "label", "list", "--repo", args.repo, "--limit", "200", "--json", "name"], text=True
    )
)
existing = {label["name"] for label in current}
for label in labels:
    if label["name"] in existing:
        continue
    print(("Creating: " if args.apply else "Would create: ") + label["name"], flush=True)
    if args.apply:
        subprocess.run(
            [
                "gh",
                "label",
                "create",
                label["name"],
                "--repo",
                args.repo,
                "--color",
                label["color"],
                "--description",
                label["description"],
            ],
            check=True,
        )
