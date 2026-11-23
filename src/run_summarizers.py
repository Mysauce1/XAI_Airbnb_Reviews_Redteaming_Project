"""
Generate paired summaries for the Airbnb red-teaming experiment.

For each selected scenario, this script generates two summaries
using the same collection of model-visible reviews:

System A: Conventional summarization
    Claude summarizes the reviews directly using the instructions
    in conventional.txt.

System B: Evidence-grounded summarization
    Claude follows the multi-stage evidence-grounding process
    implemented in evidence_grounded.py.

Running both systems on the same scenario allows their responses
to identical review manipulations to be compared.

The script supports:
- Running the complete collection of experimental scenarios.
- Running a smaller, prespecified pilot.
- Running one or more specific scenarios.
- Skipping previously completed scenarios.
- Resuming System B when System A has already finished.
- Overwriting existing outputs when explicitly requested.
- Recording source-file hashes and model configuration.

Each scenario's results are saved as a separate JSON file in
results/summaries/.

The script makes real Claude API requests and may incur API costs.
It should be run only after the adversarial scenario CSV files
have been generated and validated.
"""

from __future__ import annotations

# Provides support for command-line arguments.
#
# Used to select a pilot, specify individual scenarios,
# or request that existing outputs be overwritten.
import argparse

# Imported in the original script but not used directly.
# JSON serialization is handled by shared helper functions.
import json

# Imported in the original script but not used directly.
# Model settings are retrieved through model_clients.py.
import os

# Imported in the original script but not used directly.
# Path construction is handled through the ROOT Path object.
from pathlib import Path

# Shared experiment utilities.
from experiment_common import (
    ROOT,  # Absolute path to the project root.
    load_scenarios,  # Load and validate the scenario CSV files.
    visible_reviews,  # Prepare reviews in the model-visible format.
    write_json,  # Save results as formatted JSON.
    read_json,  # Load previously saved JSON results.
    prompt,  # Read a prompt template from prompts/.
    canonical,  # Serialize input data consistently as JSON.
    digest,  # Calculate a SHA-256 hash of a file.
)

# Claude API adapter and configured model settings.
#
# claude_json() sends a request and returns:
# - Parsed JSON output.
# - Raw response text.
# - API request ID.
# - Token usage metadata.
#
# The model and effort settings are recorded alongside
# the experimental results for traceability.
from model_clients import (
    claude_json,
    CLAUDE_MODEL,
    CLAUDE_EFFORT,
)

# Implements System B's evidence-grounded summarization workflow.
#
# This function performs evidence extraction, validation,
# organization, selection, and grounded summary generation.
from evidence_grounded import build_evidence


def main():
    """
    Run paired summarization for the selected scenarios.

    The workflow:
    1. Parses the command-line options.
    2. Loads the scenario definitions and review inputs.
    3. Determines which scenarios to run.
    4. Creates the output directory.
    5. Records hashes of the scenario source files.
    6. Runs or resumes conventional summarization (System A).
    7. Runs evidence-grounded summarization (System B).
    8. Saves both systems' outputs for later evaluation.

    Existing completed scenarios are skipped unless --overwrite
    is supplied.
    """

    # Set up the command-line interface.
    #
    # argparse handles optional arguments and generates
    # standard command-line help messages.
    ap = argparse.ArgumentParser()

    # --pilot runs a smaller collection of scenarios rather
    # than the full experiment.
    #
    # action="store_true" means the value is False unless
    # the flag is explicitly included.
    #
    # Example:
    # python src/run_summarizers.py --pilot
    #
    # The pilot is useful for checking whether the prompts,
    # API adapters, and output files work as expected before
    # committing to the full experiment.
    ap.add_argument(
        "--pilot", action="store_true", help="Use a small prespecified pilot"
    )

    # Allow specific scenario IDs to be selected.
    #
    # action="append" allows the argument to appear multiple
    # times, producing a list of requested IDs.
    #
    # Example:
    # python src/run_summarizers.py --scenario-id SCENARIO_ID
    #
    # Multiple IDs can be supplied by repeating the flag.
    #
    # If --scenario-id is provided, it takes precedence
    # over --pilot in the selection logic below.
    ap.add_argument(
        "--scenario-id", action="append", help="Run only listed scenario IDs"
    )

    # Allow existing scenario output files to be regenerated.
    #
    # By default, completed results are reused rather than
    # triggering additional API calls.
    #
    # --overwrite disables that reuse and starts each
    # selected scenario's summarization from the beginning.
    ap.add_argument("--overwrite", action="store_true")

    # Read the command-line options.
    args = ap.parse_args()

    # Load the experimental scenario definitions and review inputs.
    #
    # manifest contains one dictionary per scenario, including:
    # - Scenario ID.
    # - Listing ID.
    # - Scenario type.
    # - Attack variant.
    # - Injection intensity.
    #
    # groups maps each scenario ID to the corresponding reviews.
    #
    # load_scenarios() also validates required columns,
    # scenario IDs, and review ID uniqueness within scenarios.
    manifest, groups = load_scenarios()

    # Determine which scenarios should be processed.

    # If specific scenario IDs were supplied, retain only
    # matching entries from the manifest.
    #
    # Converting the requested IDs to a set makes membership
    # checks efficient and ignores duplicate requested IDs.
    #
    # This filter does not raise an error if a requested
    # scenario ID does not exist. Such IDs simply produce
    # no matching manifest entry.
    if args.scenario_id:
        manifest = [m for m in manifest if m["scenario_id"] in set(args.scenario_id)]

    # If no specific scenario IDs were provided but --pilot
    # was selected, construct the smaller pilot collection.
    elif args.pilot:

        # Store the scenarios selected for the pilot.
        pilot = []

        # First include one baseline-with-challenge scenario
        # for each listing.
        #
        # A baseline-with-challenge scenario contains the
        # representative reviews together with the selected
        # challenge reviews, without the additional attack
        # manipulation being tested.
        #
        # Including these scenarios provides a reference point
        # for examining whether the systems preserve important
        # concerns before adversarial reviews are injected.
        #
        # The set removes duplicate listing IDs, while sorted()
        # makes the listing iteration order predictable.
        for listing in sorted({m["listing_id"] for m in manifest}):

            # Find scenarios belonging to this listing whose
            # IDs end with "baseline_with_challenge".
            #
            # [:1] keeps only the first matching entry.
            #
            # The selected entry depends on the order of
            # the scenario manifest if multiple matches exist.
            pilot += [
                m
                for m in manifest
                if m["listing_id"] == listing
                and m["scenario_id"].endswith("baseline_with_challenge")
            ][:1]

        # Next include one medium-intensity scenario for
        # each of the four adversarial attack variants.
        #
        # This provides a small initial test of the different
        # manipulation mechanisms without running every
        # listing-intensity combination.
        #
        # The variants are:
        #
        # generic_positive_volume:
        #   Adds broadly positive reviews that may dilute
        #   the prominence of less common negative concerns.
        #
        # aspect_specific_counterevidence:
        #   Adds positive statements about the same aspect
        #   targeted by a genuine concern, creating apparently
        #   conflicting evidence.
        #
        # near_duplicate_positive:
        #   Adds similar positive reviews that may create
        #   an exaggerated impression of independent agreement.
        #
        # recent_dated_issue:
        #   Uses strategically dated reviews to influence
        #   how the model interprets the timing of an issue.
        for variant in [
            "generic_positive_volume",
            "aspect_specific_counterevidence",
            "near_duplicate_positive",
            "recent_dated_issue",
        ]:

            # Find medium-intensity scenarios for this variant.
            #
            # [:1] selects the first matching scenario across
            # all listings, not one scenario per listing.
            #
            # This means the pilot includes one medium attack
            # per variant rather than every listing-variant pair.
            pilot += [
                m
                for m in manifest
                if m["attack_variant"] == variant and m["intensity"] == "medium"
            ][:1]

        # Remove any duplicate scenarios from the pilot.
        #
        # A dictionary keyed by scenario ID keeps one entry
        # per unique scenario.
        #
        # Converting its values back to a list produces
        # the final pilot manifest.
        manifest = list({m["scenario_id"]: m for m in pilot}.values())

    # If neither --scenario-id nor --pilot was supplied,
    # the full manifest remains unchanged.
    #
    # The script will therefore consider every scenario
    # in the experiment.

    # Locate the directory where summary results are stored.
    output = ROOT / "results/summaries"

    # Create the directory if necessary.
    #
    # parents=True creates any missing parent directories.
    # exist_ok=True avoids an error if the directory exists.
    output.mkdir(parents=True, exist_ok=True)

    # Calculate SHA-256 hashes of the scenario source files.
    #
    # The hashes provide fingerprints of the exact files used
    # when the summarization results were generated.
    #
    # This helps detect changes to scenario definitions or
    # review inputs between experimental runs.
    #
    # Note that these hashes cover the two scenario CSV files.
    # They do not automatically cover prompt templates,
    # Python source code, or model configuration.
    #
    # The model and effort settings are recorded separately.
    hashes = {
        f: digest(ROOT / "data/adversarial" / f)
        for f in (
            "scenario_manifest.csv",
            "scenario_inputs.csv",
        )
    }

    # Process each selected scenario independently.
    #
    # A separate output file is used for each scenario,
    # making it possible to inspect or resume individual
    # experimental conditions.
    for m in manifest:

        # Retrieve the unique scenario identifier.
        sid = m["scenario_id"]

        # Prepare the review collection that will be shown
        # to both summarization systems.
        #
        # visible_reviews() sorts reviews chronologically,
        # assigns neutral sequential IDs, and retains
        # the review dates and text.
        #
        # Both systems receive the same prepared reviews.
        #
        # This is essential for the paired comparison:
        # differences in their outputs should not result
        # from differences in the review collections.
        reviews = visible_reviews(groups[sid])

        # Construct the JSON output path for this scenario.
        #
        # The filename is based on the scenario ID.
        path = output / f"{sid}.json"

        # Record metadata shared by both summarization systems.
        #
        # scenario_id identifies the experimental condition.
        # listing_id identifies the Airbnb property.
        # source_hashes identifies the scenario input files.
        # model and effort record the Claude configuration.
        # as_of records the experiment's temporal cutoff.
        #
        # These fields are stored alongside the summaries
        # to support later auditing and comparison.
        common = {
            "scenario_id": sid,
            "listing_id": m["listing_id"],
            "source_hashes": hashes,
            "model": CLAUDE_MODEL,
            "effort": CLAUDE_EFFORT,
            "as_of": "2026-09-30",
        }

        # Check whether this scenario already has saved results.
        #
        # Without --overwrite, an existing JSON file is loaded
        # so completed work can be reused.
        #
        # With --overwrite, existing is set to None and the
        # scenario is regenerated from the beginning.
        existing = read_json(path) if path.exists() and not args.overwrite else None

        # Validate previously saved results before reusing them.
        if existing:

            # Compare the saved source hashes and model settings
            # with the configuration for the current run.
            #
            # This prevents the script from silently combining
            # outputs generated using different scenario files,
            # model identifiers, effort settings, or cutoff dates.
            #
            # If any tracked setting differs, the script stops
            # and requires an explicit overwrite.
            #
            # This is a partial reproducibility safeguard:
            # changes to prompt text or implementation code
            # are not detected by these particular checks.
            for key in (
                "source_hashes",
                "model",
                "effort",
                "as_of",
            ):
                if existing.get(key) != common.get(key):
                    raise RuntimeError(
                        f"{sid}: saved {key} differs; "
                        "archive old outputs and use --overwrite"
                    )

            # Skip scenarios whose paired summaries are
            # already marked complete.
            #
            # This avoids unnecessary repeat API requests
            # and helps conserve experiment costs.
            #
            # The script relies on the saved status field
            # rather than independently revalidating every
            # field in the completed output.
            if existing.get("status") == "complete":
                print("Skipping completed:", sid)
                continue

        # Run or resume System A: conventional summarization.

        # If an incomplete result already contains a nonempty
        # System A summary, reuse it.
        #
        # This is particularly useful if a previous run
        # completed System A but failed during System B.
        #
        # Reusing the saved output avoids repeating the
        # conventional summarization API request.
        if existing and existing.get("system_a", {}).get("summary"):

            system_a = existing["system_a"]

            # Report that System A is being reused and the
            # script is continuing with System B.
            print("Resuming System B for:", sid)

        else:

            # Send the full review collection to Claude using
            # the conventional summarization prompt.
            #
            # This system summarizes the supplied reviews
            # directly rather than first constructing an
            # explicit evidence ledger.
            #
            # The payload contains:
            # - The experiment cutoff date.
            # - The prepared review collection.
            #
            # No ground-truth labels or synthetic-review
            # indicators are supplied.
            #
            # max_tokens=2500 limits the response length.
            #
            # This is a real Claude API request.
            a, raw_a, request_id, usage_a = claude_json(
                prompt("conventional.txt"),
                canonical(
                    {
                        "as_of": "2026-09-30",
                        "reviews": reviews,
                    }
                ),
                max_tokens=2500,
            )

            # Verify that Claude returned a summary string.
            #
            # This catches missing or incorrectly typed
            # summary fields before the result is saved.
            #
            # It does not evaluate the summary's accuracy,
            # completeness, or resistance to manipulation.
            if not isinstance(a.get("summary"), str):
                raise ValueError("Missing conventional summary")

            # Store the conventional summary and API metadata.
            #
            # Keeping the raw response allows later inspection
            # of what Claude actually returned.
            #
            # The request ID and usage information support
            # traceability and cost analysis.
            system_a = {
                "summary": a["summary"],
                "raw_response": raw_a,
                "request_id": request_id,
                "usage": usage_a,
            }

            # Save System A immediately after it finishes.
            #
            # The status "system_b_pending" indicates that
            # the conventional summary is available but the
            # evidence-grounded summary is not yet complete.
            #
            # This checkpoint is important because System B
            # makes multiple API requests and may take longer.
            #
            # If System B fails or the script is interrupted,
            # System A's result can be reused on the next run.
            write_json(
                path,
                {
                    **common,
                    "system_a": system_a,
                    "status": "system_b_pending",
                },
            )

        # Run System B: evidence-grounded summarization.
        #
        # build_evidence() processes the same reviews through
        # its multi-stage evidence-grounding workflow:
        #
        # 1. Extract evidence from the reviews.
        # 2. Validate quotations and organize an evidence ledger.
        # 3. Select claims using the ledger.
        # 4. Generate a summary from the selected claims.
        #
        # The function returns the final summary together
        # with citations, the evidence ledger, selected claims,
        # rejected evidence, raw responses, request IDs,
        # and token usage information.
        #
        # This is a real API operation and can involve
        # several Claude requests for one scenario.
        b = build_evidence(reviews)

        # Save the complete paired result.
        #
        # Both systems' outputs are stored together under
        # the same scenario ID.
        #
        # This structure makes it easier to compare their
        # summaries and connect them to later claim audits
        # and human ground-truth evaluations.
        #
        # The status is set to "complete" only after
        # System B returns successfully.
        write_json(
            path,
            {
                **common,
                "system_a": system_a,
                "system_b": b,
                "status": "complete",
            },
        )

        # Confirm that the scenario output was saved.
        print("Saved", path)


# Run the experiment only when this script is executed directly.
#
# Importing the module does not automatically generate summaries
# or make API requests.
if __name__ == "__main__":
    main()
