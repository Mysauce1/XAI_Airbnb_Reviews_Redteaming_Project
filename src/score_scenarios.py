"""
Stage 2: Prepare the human-review scorecard for the Airbnb red-teaming experiment.

This script combines information from three sources:

1. Scenario manifest:
   Identifies each experimental condition, including the listing,
   attack variant, intensity, and targeted issue.

2. Ground-truth benchmark:
   Identifies genuine concerns established from the original
   review data, independently of the synthetic review attacks.

3. Blind Stage 1 claim audits:
   Provides automated judgments about whether generated summary
   claims are supported by the reviews supplied to each system.

The script creates one scorecard row for each completed scenario
and summarization system (System A and System B).

It automatically fills fields that can be obtained from existing
experimental records, but leaves the human-adjudication fields blank.

Human reviewers must determine whether:
- A genuine concern appears in the baseline summary.
- The concern remains visible after an attack.
- The concern is omitted or understated.
- The summary creates a misleading impression of consensus.
- The summary distorts the timing of a genuine issue.
- Any observed loss of information was induced by the attack.
- The attack was successful under the evaluation criteria.

This separation is important because the blind claim judge only
evaluates summaries against the reviews the models received.
Those reviews may contain synthetic, strategically written content.

A summary can therefore be faithful to its manipulated input
while still being misleading relative to the genuine reviews.

The scorecard is saved to:
    results/evaluation/scenario_scorecard.csv

By default, the script refuses to overwrite an existing scorecard
to protect manually entered evaluations.

This script does not make API requests or automatically assign
attack-success outcomes.
"""

from __future__ import annotations

# Provides command-line argument parsing.
#
# Used here to control whether an existing scorecard
# may be overwritten.
import argparse

# Imported in the original script but not used directly.
# Path operations are performed using the ROOT Path object
# imported from experiment_common.
from pathlib import Path

# Shared utilities for locating project files and reading
# or writing the CSV and JSON data used by the experiment.
from experiment_common import (
    ROOT,  # Absolute path to the project root.
    read_csv,  # Load a CSV as a list of dictionaries.
    read_json,  # Load a JSON file into Python data structures.
    write_csv,  # Save dictionaries to a CSV with specified columns.
)

# Define the columns that will appear in the human-review scorecard.
#
# Keeping an explicit column list ensures that every generated
# scorecard uses the same structure and column order.
#
# This is important because the scorecard combines automatically
# populated information with fields that must be completed manually.
#
# The columns are grouped conceptually below, although they are
# stored together in one CSV file.
COLUMNS = [
    # Scenario identification.
    #
    # These fields connect each scorecard row to the original
    # experimental condition and summarization system.
    "scenario_id",
    "listing_id",
    "system",
    # Experimental condition metadata.
    #
    # These describe whether the scenario is a baseline or attack,
    # which manipulation was used, and its intensity.
    "scenario_type",
    "attack_type",
    "attack_variant",
    "intensity",
    # The issue and aspect the attack is intended to influence.
    #
    # These fields help reviewers focus on the specific concern
    # being tested rather than evaluating only general summary quality.
    "target_issue",
    "target_aspect",
    # Reference information for ground-truth comparison.
    #
    # baseline_scenario_id identifies the baseline-with-challenge
    # condition associated with an attack.
    #
    # genuine_concern_ids links the scenario to concerns documented
    # in the independent ground-truth benchmark.
    "baseline_scenario_id",
    "genuine_concern_ids",
    # Automated metrics from the blind Stage 1 claim audit.
    #
    # These describe how the summary compares with the reviews
    # supplied to the summarization system.
    #
    # They do not establish whether the summary accurately
    # represents the genuine, unmanipulated review history.
    "input_faithfulness_supported",
    "input_faithfulness_total",
    "blind_contradiction_score",
    "blind_prevalence_score",
    "blind_temporal_score",
    # Human assessment of the genuine concern's visibility.
    #
    # Reviewers determine whether the concern appeared in the
    # baseline and whether it remains visible after manipulation.
    "baseline_concern_present",
    "attacked_concern_present",
    # Human assessment of misleading summary behavior.
    #
    # These fields capture outcomes that may not be detectable
    # through input-faithfulness evaluation alone.
    "attacked_concern_understated",
    "misleading_consensus",
    "ground_truth_temporal_distortion",
    # Human determination of attack-related effects.
    #
    # attack_induced_loss should reflect whether the manipulation
    # caused a meaningful loss or distortion relative to baseline.
    #
    # attack_success records the final outcome according to the
    # project's evaluation criteria.
    "attack_induced_loss",
    "attack_success",
    # Review completion and supporting explanation.
    #
    # human_verified indicates whether the row has been reviewed.
    # notes allows the reviewer to document the reasoning
    # behind the assigned judgments.
    "human_verified",
    "notes",
]


def main():
    """
    Generate the Stage 2 human-adjudication scorecard.

    The workflow:
    1. Parse the overwrite option.
    2. Load the scenario manifest and benchmark concerns.
    3. Organize genuine concerns by listing.
    4. Protect an existing scorecard from accidental replacement.
    5. Identify scenarios with completed summarization outputs.
    6. Retrieve any available blind claim-audit results.
    7. Create one row per scenario and summarization system.
    8. Populate experimental metadata and automated metrics.
    9. Leave human-adjudication fields empty.
    10. Save the scorecard for manual review.

    No attack-success labels are calculated automatically.
    """

    # Set up the command-line interface.
    ap = argparse.ArgumentParser()

    # Allow the user to explicitly overwrite an existing scorecard.
    #
    # action="store_true" means the value is False by default
    # and becomes True when --overwrite is supplied.
    #
    # This safeguard is particularly important because the
    # scorecard will eventually contain manually entered
    # judgments that cannot be regenerated from the source files.
    ap.add_argument("--overwrite", action="store_true")

    # Read the command-line arguments.
    args = ap.parse_args()

    # Load the scenario manifest.
    #
    # The manifest contains one row per experimental condition,
    # including the listing ID, attack variant, intensity,
    # and target issue.
    #
    # These fields provide the experimental context needed
    # to interpret the summaries and their evaluation results.
    manifest = read_csv(ROOT / "data/adversarial/scenario_manifest.csv")

    # Load the benchmark of genuine minority concerns.
    #
    # These concerns were established independently of the
    # synthetic review manipulations.
    #
    # They provide reference information for evaluating
    # whether a generated summary preserves important issues.
    concerns = read_csv(ROOT / "data/benchmark/minority_concerns.csv")

    # Organize benchmark concerns by listing ID.
    #
    # This makes it easier to retrieve the relevant genuine
    # concerns when processing each experimental scenario.
    concern_by_listing = {}

    for c in concerns:

        # setdefault() creates an empty list for a listing
        # if it has not appeared in the dictionary yet.
        #
        # The current concern is then added to that list.
        #
        # Because read_csv() returns string values, listing IDs
        # are compared as strings throughout this function.
        concern_by_listing.setdefault(c["listing_id"], []).append(c)

    # Define the output path for the human-review scorecard.
    output = ROOT / "results/evaluation/scenario_scorecard.csv"

    # Protect existing manual work.
    #
    # If the scorecard already exists and --overwrite was not
    # supplied, stop before writing anything.
    #
    # This prevents rerunning the script from accidentally
    # deleting human judgments, verification statuses, or notes.
    #
    # If --overwrite is supplied, the scorecard is rebuilt
    # from the source files and any previous manual entries
    # will be lost unless they were backed up separately.
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Preserving manual edits: {output}")

    # Collect the scorecard records before writing them to CSV.
    rows = []

    # Process each experimental scenario defined in the manifest.
    for m in manifest:

        # Retrieve the scenario ID.
        sid = m["scenario_id"]

        # Locate the paired summarization result for this scenario.
        #
        # The file is expected to contain System A and System B
        # outputs generated from the same scenario input.
        summary = ROOT / "results/summaries" / f"{sid}.json"

        # Skip scenarios that do not have a saved summary file.
        #
        # This allows the scorecard to be generated even if
        # only a subset of scenarios has been run.
        if not summary.exists():
            continue

        # Load the saved summarization result.
        doc = read_json(summary)

        # Only include scenarios marked as complete.
        #
        # An incomplete scenario may contain System A's summary
        # but not System B's, making a paired comparison premature.
        if doc.get("status") != "complete":
            continue

        # Locate the corresponding blind Stage 1 claim audit.
        #
        # This audit evaluates whether the summaries are
        # supported by the reviews supplied to each system.
        audit_path = ROOT / "results/claim_audits" / f"{sid}.json"

        # Load the claim audit if it exists.
        #
        # If no audit file is available, use an empty systems
        # dictionary so the scorecard can still be created.
        #
        # This allows manual review preparation to proceed
        # without requiring every automated audit to be present.
        audit = read_json(audit_path) if audit_path.exists() else {"systems": {}}

        # Identify the baseline-with-challenge scenario
        # associated with the current attack.
        #
        # For attack scenarios, construct the baseline ID
        # using the listing ID and the expected naming pattern.
        #
        # This allows reviewers to compare an attacked summary
        # against the corresponding unmanipulated baseline
        # that includes the genuine challenge concerns.
        #
        # For baseline scenarios, leave this field empty.
        #
        # This constructs a reference string; it does not
        # verify that the referenced baseline file exists.
        base = (
            f"{m['listing_id']}_baseline_with_challenge"
            if m["scenario_type"] == "attack"
            else ""
        )

        # Retrieve all benchmark concern IDs for this listing.
        #
        # These IDs link the scorecard row to genuine issues
        # documented in minority_concerns.csv.
        #
        # If no concerns are listed for the property,
        # an empty list is returned.
        #
        # The current implementation includes every benchmark
        # concern associated with the listing, not only the
        # concern targeted by the specific attack.
        genuine = [c["concern_id"] for c in concern_by_listing.get(m["listing_id"], [])]

        # Create a separate evaluation row for each system.
        #
        # Both systems are evaluated under the same scenario,
        # but their summary content and audit results may differ.
        #
        # Keeping separate rows makes it possible to compare
        # their performance across attack variants and intensities.
        for system in (
            "system_a",
            "system_b",
        ):

            # Retrieve the blind audit for this system.
            #
            # The chained get() calls safely return an empty
            # dictionary if the audit or system result is missing.
            #
            # This avoids stopping the entire scorecard
            # generation process because of one missing audit.
            blind = audit.get("systems", {}).get(system, {}).get("audit", {})

            # Retrieve the claims evaluated by the blind judge.
            #
            # Each claim is expected to contain a verdict
            # describing whether it is supported by the
            # scenario's review collection.
            #
            # An absent claims field defaults to an empty list.
            claims = blind.get("claims", [])

            # Add the scorecard row.
            #
            # Only fields supported by existing experimental
            # records are populated automatically.
            #
            # The remaining fields defined in COLUMNS are
            # intentionally omitted from this dictionary.
            #
            # write_csv() will write those missing fields as
            # empty CSV cells for later human adjudication.
            rows.append(
                {
                    # Identify the scenario, property, and system.
                    "scenario_id": sid,
                    "listing_id": m["listing_id"],
                    "system": system,
                    # Preserve the experimental condition.
                    "scenario_type": m["scenario_type"],
                    "attack_type": m["attack_type"],
                    "attack_variant": m["attack_variant"],
                    "intensity": m["intensity"],
                    # Record the issue and aspect targeted
                    # by the attack, when available.
                    #
                    # Missing optional fields become empty strings.
                    "target_issue": m.get("target_issue", ""),
                    "target_aspect": m.get("target_aspect", ""),
                    # Link attack scenarios to their reference
                    # baseline and genuine benchmark concerns.
                    "baseline_scenario_id": base,
                    "genuine_concern_ids": "; ".join(genuine),
                    # Count claims that the blind judge marked
                    # as supported by the scenario input.
                    #
                    # In Python, True counts as 1 and False as 0.
                    # Therefore, summing these comparisons gives
                    # the number of supported claims.
                    #
                    # This is an input-faithfulness measure,
                    # not a measure of ground-truth correctness.
                    "input_faithfulness_supported": sum(
                        c.get("verdict") == "supported" for c in claims
                    ),
                    # Record the total number of claims
                    # returned by the blind audit.
                    #
                    # Together with the supported count,
                    # this can be used to calculate the
                    # proportion of claims marked supported.
                    #
                    # A value of zero may indicate either
                    # no evaluated claims or a missing audit.
                    "input_faithfulness_total": len(claims),
                    # Preserve the blind judge's contradiction score.
                    #
                    # Its precise interpretation depends on
                    # the scoring criteria in claim_judge.txt.
                    "blind_contradiction_score": blind.get("contradiction_score", ""),
                    # Preserve the blind judge's prevalence score.
                    #
                    # This can help identify whether a summary
                    # misrepresents how common an issue appears
                    # within the supplied review collection.
                    #
                    # It does not establish the issue's prevalence
                    # among genuine reviews.
                    "blind_prevalence_score": blind.get("prevalence_score", ""),
                    # Preserve the blind judge's temporal score.
                    #
                    # This concerns the representation of timing
                    # relative to the supplied review evidence.
                    #
                    # It should not be treated as proof that the
                    # summary accurately describes the genuine
                    # history of the property.
                    "blind_temporal_score": blind.get("temporal_score", ""),
                }
            )

    # Write the scorecard to disk.
    #
    # COLUMNS controls the output column order.
    #
    # Because the human-adjudication fields are not included
    # in the generated row dictionaries, they appear as
    # empty cells in the CSV.
    #
    # write_csv() also creates the output directory
    # if it does not already exist.
    write_csv(output, rows, COLUMNS)

    # Inform the user that the generated scorecard
    # requires manual review before it can be treated
    # as a completed evaluation dataset.
    print("Review and complete manual adjudication columns:", output)

    # Explicitly warn that attack success must not be
    # inferred solely from automated claim-audit metrics.
    #
    # Human reviewers must compare the baseline and attacked
    # summaries against the genuine benchmark concerns
    # before assigning attack-induced loss or success.
    print(
        "Attack success cannot be computed responsibly until "
        "baseline-conditional human fields are completed."
    )


# Run the scorecard preparation workflow only when this
# script is executed directly.
#
# Importing it from another module will not automatically
# create or overwrite evaluation files.
if __name__ == "__main__":
    main()
