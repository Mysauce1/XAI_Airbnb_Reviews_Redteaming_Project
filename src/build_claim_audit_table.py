"""
Build the claim-audit table from the blind judge's JSON outputs.

Run from the project root after src/run_claim_audit.py:
    python src/build_claim_audit_table.py

Reads every results/claim_audits/<scenario_id>.json and writes one row per
judged claim to results/evaluation/claim_audit.csv, using the columns of
data/evaluation/claim_audit_template.csv.

The judge fills the claim, verdict, review-ID and reason columns. The
human_verdict and notes columns are for the human reviewer. If the output file
already exists, any human_verdict and notes already entered are carried over
(matched on scenario_id, system and claim_id), so rerunning never erases manual
review work. No API requests are made.
"""

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "results" / "claim_audits"
TEMPLATE = ROOT / "data" / "evaluation" / "claim_audit_template.csv"
DEFAULT_OUTPUT = ROOT / "results" / "evaluation" / "claim_audit.csv"
SYSTEMS = ("system_a", "system_b")
HUMAN_COLUMNS = ("human_verdict", "notes")


def read_columns(template: Path) -> list[str]:
    """Return the column names from the template's header row."""
    with template.open(newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def read_existing_human_review(path: Path) -> dict:
    """Map (scenario_id, system, claim_id) to the human columns already filled in."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {
            (r["scenario_id"], r["system"], r["claim_id"]): {c: r.get(c, "") for c in HUMAN_COLUMNS}
            for r in csv.DictReader(f)
        }


def judge_rows(audit_dir: Path):
    """Yield one table row per claim from each scenario's judge JSON."""
    paths = sorted(audit_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"No judge outputs found in {audit_dir}. Run src/run_claim_audit.py first.")
    for path in paths:
        audit = json.loads(path.read_text(encoding="utf-8"))
        for system in SYSTEMS:
            if system not in audit.get("systems", {}):
                print(f"Skipping {path.name} {system}: no completed audit")
                continue
            claims = audit["systems"][system]["audit"]["claims"]
            # Claim IDs follow the judge's claim order: C01, C02, ...
            for number, claim in enumerate(claims, start=1):
                yield {
                    "scenario_id": audit["scenario_id"],
                    "system": system,
                    "claim_id": f"C{number:02d}",
                    "claim_text": claim["claim"],
                    "verdict": claim["verdict"],
                    "supporting_review_ids": "; ".join(claim["supporting_review_ids"]),
                    "contradicting_review_ids": "; ".join(claim["contradicting_review_ids"]),
                    "reason": claim["reason"],
                    "judge_model": audit["judge_model"],
                    "human_verdict": "",
                    "notes": "",
                }


def main() -> None:
    ap = argparse.ArgumentParser(description="Flatten judge JSONs into the claim-audit table.")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                    help="Output CSV (default: results/evaluation/claim_audit.csv)")
    args = ap.parse_args()

    columns = read_columns(TEMPLATE)
    existing = read_existing_human_review(args.output)

    rows, carried = [], 0
    for row in judge_rows(AUDIT_DIR):
        saved = existing.get((row["scenario_id"], row["system"], row["claim_id"]))
        if saved:
            row.update(saved)
            carried += any(saved.values())
        rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} claims to {args.output}")
    print(f"Kept existing human review on {carried} claims; fill human_verdict and notes for any others you review.")


if __name__ == "__main__":
    main()
