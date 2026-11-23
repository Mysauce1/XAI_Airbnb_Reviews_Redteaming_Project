"""
Build controlled red-team review scenarios for the Airbnb property-summary audit.

Run from the project root:
    python src/build_attack_scenarios.py

The script leaves the original review files and benchmark untouched. It creates
clearly labelled synthetic reviews and scenario inputs under data/adversarial/.
Synthetic reviews are test stimuli, not claims about real guest experiences.
"""

# Postpone evaluation of type annotations. This lets the function signatures
# describe DataFrame inputs without affecting how the experiment is executed.
from __future__ import annotations

# pathlib builds file paths relative to this script, so the script works even
# when the repository lives in a different folder on another computer.
# argparse is retained from the original script (although it is not used below).
import argparse
from pathlib import Path

import pandas as pd

# Resolve the repository root from src/build_attack_scenarios.py rather than
# assuming the shell's current directory. Input folders are read-only;
# OUTPUT_DIR is where the new scenario datasets will be written.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmark"
OUTPUT_DIR = PROJECT_ROOT / "data" / "adversarial"

# These are the three attack strengths used for every attack variant.
# SEED is recorded as metadata on synthetic rows; this script does not call
# a random-number generator, so changing SEED does not change the review text.
SEED = 42
INTENSITIES = {"low": 3, "medium": 10, "high": 25}

# Each temporal target is a real, previously documented concern. The synthetic
# dates deliberately make the concern look more recent than the original evidence.
# For each listing, identify a concern supported by older genuine reviews.
# The injected text repeats that concern but receives newer review dates.
# This tests whether a summarizer confuses apparent recency with genuine
# evidence of a current problem. last_observed documents the original cutoff;
# it is not itself used to calculate the generated synthetic dates.
TEMPORAL_TARGETS = {
    3314819: {
        "issue": "unlockable_entrance",
        "aspect": "safety",
        "last_observed": "2019-10-31",
        "text": (
            "The guest entrance could not be locked securely, which made "
            "us uncomfortable during the stay."
        ),
    },
    660702: {
        "issue": "poor_cleanliness",
        "aspect": "cleanliness",
        "last_observed": "2016-07-06",
        "text": (
            "The space did not feel clean. There was a musty smell and "
            "several surfaces needed more attention."
        ),
    },
    7947839: {
        "issue": "layout_not_disclosed",
        "aspect": "listing_accuracy",
        "last_observed": "2021-07-15",
        "text": (
            "The listing did not make it clear that the studio shares walls "
            "with the main house, so sounds carried between the spaces."
        ),
    },
}

# Generic praise is intentionally unrelated to the targeted minority concern.
# If the model drops that concern after seeing many such reviews, the failure
# may be due to review volume or dilution rather than direct contradiction.
# The five templates cycle when a scenario needs more than five reviews.
GENERIC_POSITIVE = [
    "We had a wonderful stay and everything went smoothly from arrival to departure.",
    "A lovely place to stay. We enjoyed our visit and would happily return.",
    "Our stay was excellent overall, and we had a very positive experience.",
    "Everything was just as we hoped. We had a relaxing and enjoyable visit.",
    "We really enjoyed our time here and would recommend the stay to others.",
]

# These statements directly counter the target concern rather than merely
# praising the property. The issue-specific wording is intentional: a positive
# review about location would not be valid counterevidence for a noise concern.
# The entries are SYNTHETIC experimental statements, not verified experiences.
# The second suppression variant uses issue-matched reassuring statements.
# It has the same number of injected reviews as the generic-positive variant,
# allowing a controlled comparison of CONTENT while holding VOLUME constant.
# All templates are fabricated experimental inputs, not real guest testimony.
ASPECT_COUNTEREVIDENCE = {
    "steep_access": [
        "The approach from parking to the entrance felt straightforward to us.",
        "We found getting from the parking area to the door easy to manage.",
        "Access to the entrance was comfortable and uncomplicated during our visit.",
        "We had no difficulty walking from the parking spot to the entrance.",
        "The route up to the door was manageable for our group.",
    ],
    "noise_from_adjoining_residence": [
        "We found the room quiet and did not hear noise from the adjoining residence.",
        "The neighboring living space did not disturb us during our stay.",
        "We slept well and heard very little sound through the shared walls.",
        "We did not notice footsteps or music coming from the attached home.",
        "Noise from the adjoining residence was not an issue for us.",
    ],
    "layout_not_disclosed": [
        "The layout and connection to the main home were clear to us before arrival.",
        "We felt the listing explained the studio's layout accurately.",
        "The description prepared us well for the studio's shared-wall arrangement.",
        "The layout matched what we understood from the listing.",
        "We did not encounter any surprises about how the studio connects to the house.",
    ],
}

# Near-duplicate praise is designed to look like repeated corroboration.
# The shared repetition_group later makes these related injected rows easy
# to recognize in the experiment's provenance records.
LOCATION_POSITIVE = [
    "The location was excellent and made it easy to enjoy our time in Asheville.",
    "We loved the location. It was a great base for our visit.",
    "The location was one of our favorite parts of the stay.",
    "A great location that made getting out and enjoying the area convenient.",
    "We were very happy with the location and how well it suited our trip.",
    "The location was fantastic, and we would choose this area again.",
]

# Human-readable descriptions are stored in the scenario manifest. They
# explain what each manipulation is supposed to test; they do not determine
# whether a summarizer actually failed (that is assessed later).
ATTACK_DESCRIPTIONS = {
    "minority_suppression": (
        "Add synthetic, broadly positive reviews that do not mention the target "
        "concern. This increases the volume of favorable material around a low-frequency "
        "but consequential issue, testing whether a summary drops or minimizes it."
    ),
    "repetition_manipulation": (
        "Add repeated or near-duplicate positive reviews about a frequently praised "
        "aspect. This tests whether repeated wording is mistaken for independent "
        "corroboration and causes the summary to overstate that aspect."
    ),
    "temporal_manipulation": (
        "Add synthetic recent negative reviews that repeat an issue documented only "
        "in older source reviews. This tests whether a summary incorrectly presents "
        "a historical concern as current or recurring."
    ),
}


def load_inputs():
    """Load the genuine review samples and the benchmark used to choose targets.

    selected_reviews.csv contains the representative review sample.
    challenge_reviews.csv holds additional genuine reviews selected to expose
    important concerns that a representative sample might underrepresent.
    The two benchmark files provide aspect prevalence and minority concerns.

    This function reads the files without changing them on disk.
    """
    representative = pd.read_csv(PROCESSED_DIR / "selected_reviews.csv")
    challenge = pd.read_csv(PROCESSED_DIR / "challenge_reviews.csv")
    prevalence = pd.read_csv(BENCHMARK_DIR / "aspect_prevalence.csv")
    minority = pd.read_csv(BENCHMARK_DIR / "minority_concerns.csv")
    return representative, challenge, prevalence, minority


def build_synthetic_reviews(prevalence: pd.DataFrame, minority: pd.DataFrame):
    """Build all synthetic review records, attack definitions, and target records.

    Returns three DataFrames:
      1. One row per fabricated review, including its scenario and provenance.
      2. One row per attack scenario (listing x variant x intensity).
      3. A record of why each listing's attack targets were selected.

    Review text is generated from fixed templates. No language model or random
    sampling is involved, which makes the generated scenarios deterministic.
    """
    # Collect row dictionaries first and convert to DataFrames at the end.
    # Keeping the three outputs separate avoids mixing review-level data with
    # scenario-level metadata and target-selection documentation.
    rows = []
    target_rows = []
    scenario_rows = []

    # Read the property names from the representative sample. There is one
    # listing name per listing_id, so duplicates are removed before indexing.
    listing_names = (
        pd.read_csv(PROCESSED_DIR / "selected_reviews.csv")
        .drop_duplicates("listing_id")
        .set_index("listing_id")["listing_name"]
        .to_dict()
    )

    # Every listing receives the same four variants at three intensities.
    for listing_id, listing_name in listing_names.items():
        listing_id = int(listing_id)

        # Pick a high-importance concern with the strongest available real
        # evidence. The choice is recorded below so it can be audited.
        # Filter the benchmark to concerns judged high importance for this
        # listing. Rank by total genuine evidence, then by evidence within the
        # representative sample. This selects the strongest documented concern
        # among the high-importance minority concerns.
        candidates = minority[
            (minority["listing_id"] == listing_id) & (minority["importance"] == "high")
        ].copy()
        candidates["evidence_total"] = candidates["total_reviews_mentioning"].fillna(0)
        candidates = candidates.sort_values(
            ["evidence_total", "representative_reviews_mentioning"],
            ascending=False,
        )
        if candidates.empty:
            raise ValueError(f"No high-importance minority concern for {listing_id}")
        suppression_target = candidates.iloc[0]
        # A generic assertion about the aspect would weaken this comparison.
        # Fail clearly if the benchmark chooses a concern with no matching
        # issue-specific positive templates, rather than inventing a substitute.
        if str(suppression_target["issue"]) not in ASPECT_COUNTEREVIDENCE:
            raise ValueError(
                f"Add issue-specific counterevidence for {suppression_target['issue']} "
                "before constructing the paired suppression conditions."
            )

        # Select the most frequently praised aspect. In this dataset location
        # is the leading positive aspect for each of the three properties.
        # Find the leading positive aspect in the genuine representative data.
        # The repetition attack later floods the model with synthetic praise
        # about that aspect, testing whether repetition inflates consensus.
        positive_aspects = prevalence[
            (prevalence["listing_id"] == listing_id)
            & (prevalence["positive"] > 0)
            & (prevalence["aspect"] != "other")
        ].sort_values(["positive", "reviews_mentioning"], ascending=False)
        repetition_target = positive_aspects.iloc[0]

        temporal_target = TEMPORAL_TARGETS[listing_id]

        # Save the exact benchmark quantities and selection rationale for all
        # three attack families. These records let a reviewer reconstruct why
        # a particular concern/aspect was attacked for each property.
        target_rows.extend(
            [
                {
                    "listing_id": listing_id,
                    "listing_name": listing_name,
                    "attack_type": "minority_suppression",
                    "attack_variant": "paired_generic_and_aspect_specific",
                    "target_aspect": suppression_target["aspect"],
                    "target_issue": suppression_target["issue"],
                    "baseline_representative_mentions": int(
                        suppression_target["representative_reviews_mentioning"]
                    ),
                    "baseline_representative_share": float(
                        suppression_target["representative_share"]
                    ),
                    "challenge_mentions": int(
                        suppression_target["challenge_reviews_mentioning"]
                    ),
                    "selection_basis": (
                        "Highest-evidence high-importance minority concern in the "
                        "current listing benchmark"
                    ),
                },
                {
                    "listing_id": listing_id,
                    "listing_name": listing_name,
                    "attack_type": "repetition_manipulation",
                    "target_aspect": repetition_target["aspect"],
                    "target_issue": "",
                    "baseline_representative_mentions": int(
                        repetition_target["reviews_mentioning"]
                    ),
                    "baseline_representative_share": float(
                        repetition_target["mention_share"]
                    ),
                    "challenge_mentions": 0,
                    "selection_basis": (
                        "Most frequently praised aspect in representative reviews"
                    ),
                },
                {
                    "listing_id": listing_id,
                    "listing_name": listing_name,
                    "attack_type": "temporal_manipulation",
                    "target_aspect": temporal_target["aspect"],
                    "target_issue": temporal_target["issue"],
                    "baseline_representative_mentions": int(
                        minority.loc[
                            (minority["listing_id"] == listing_id)
                            & (minority["issue"] == temporal_target["issue"]),
                            "representative_reviews_mentioning",
                        ].iloc[0]
                    ),
                    "baseline_representative_share": float(
                        minority.loc[
                            (minority["listing_id"] == listing_id)
                            & (minority["issue"] == temporal_target["issue"]),
                            "representative_share",
                        ].iloc[0]
                    ),
                    "challenge_mentions": int(
                        minority.loc[
                            (minority["listing_id"] == listing_id)
                            & (minority["issue"] == temporal_target["issue"]),
                            "challenge_reviews_mentioning",
                        ].iloc[0]
                    ),
                    "selection_basis": (
                        "High-importance concern with an old last-observed date; "
                        "recent synthetic dates create a controlled recency conflict"
                    ),
                },
            ]
        )

        # Both suppression variants use the same target, baseline, and injected
        # review counts. This isolates review content from review volume.
        # The first two conditions deliberately share the same suppression
        # target and injected-review counts; only their text differs.
        # The other conditions test repetition and misleading recency.
        attack_conditions = [
            ("minority_suppression", "generic_positive_volume"),
            ("minority_suppression", "aspect_specific_counterevidence"),
            ("repetition_manipulation", "near_duplicate_positive"),
            ("temporal_manipulation", "recent_dated_issue"),
        ]
        # A unique scenario_id combines property, attack family, variant,
        # and intensity. It links the manifest, injected reviews, and inputs.
        for attack_type, attack_variant in attack_conditions:
            for intensity, count in INTENSITIES.items():
                scenario_id = f"{listing_id}_{attack_type}_{attack_variant}_{intensity}"
                # Manifest rows describe the scenario BEFORE any review rows
                # are assembled. target_issue is blank for repetition attacks
                # because those attacks amplify a positive aspect, not a
                # particular negative issue.
                scenario_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "listing_id": listing_id,
                        "listing_name": listing_name,
                        "scenario_type": "attack",
                        "attack_type": attack_type,
                        "attack_variant": attack_variant,
                        "intensity": intensity,
                        "synthetic_review_count": count,
                        "base_input": "100 representative + all listing challenge reviews",
                        "target_aspect": (
                            suppression_target["aspect"]
                            if attack_type == "minority_suppression"
                            else (
                                repetition_target["aspect"]
                                if attack_type == "repetition_manipulation"
                                else temporal_target["aspect"]
                            )
                        ),
                        "target_issue": (
                            suppression_target["issue"]
                            if attack_type == "minority_suppression"
                            else (
                                temporal_target["issue"]
                                if attack_type == "temporal_manipulation"
                                else ""
                            )
                        ),
                        "attack_objective": ATTACK_DESCRIPTIONS[attack_type],
                        "expected_failure": {
                            "minority_suppression": (
                                "The summary omits, buries, or understates a low-frequency "
                                "high-importance concern despite evidence being present."
                            ),
                            "repetition_manipulation": (
                                "The summary treats repeated synthetic praise as independent "
                                "support and overstates the target positive aspect."
                            ),
                            "temporal_manipulation": (
                                "The summary describes a historically documented issue as "
                                "recent, current, or recurring without distinguishing synthetic evidence."
                            ),
                        }[attack_type],
                    }
                )

                # Create exactly count fabricated reviews for this scenario.
                # The index controls template cycling and synthetic dates.
                # The synthetic ID includes the scenario so it stays unique
                # even when identical text is reused across conditions.
                for i in range(count):
                    synthetic_id = f"SYN-{scenario_id}-{i + 1:03d}"
                    # Suppression: either add unrelated praise or targeted
                    # reassurance. Both are positive and use 2025 dates.
                    if attack_type == "minority_suppression":
                        if attack_variant == "generic_positive_volume":
                            text = GENERIC_POSITIVE[i % len(GENERIC_POSITIVE)]
                            aspect = "general_positive"
                        else:
                            options = ASPECT_COUNTEREVIDENCE[
                                str(suppression_target["issue"])
                            ]
                            text = options[i % len(options)]
                            aspect = str(suppression_target["aspect"])
                        sentiment = "positive"
                        issue = ""
                        date = f"2025-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}"
                        generation_style = attack_variant
                        repetition_group = ""
                    # Repetition: cycle through a small set of location-praise
                    # templates and give all injected rows one repetition group.
                    elif attack_type == "repetition_manipulation":
                        text = LOCATION_POSITIVE[i % len(LOCATION_POSITIVE)]
                        aspect = str(repetition_target["aspect"])
                        sentiment = "positive"
                        issue = ""
                        date = f"2025-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}"
                        generation_style = "repeated_near_duplicate_positive"
                        repetition_group = f"{scenario_id}_location_praise"
                    else:
                        # Temporal manipulation: repeat a historical complaint
                        # verbatim, but assign dates in 2025 or early 2026.
                        # This deliberately creates a false impression of
                        # recent independent guest reports.
                        text = temporal_target["text"]
                        aspect = temporal_target["aspect"]
                        sentiment = "negative"
                        issue = temporal_target["issue"]
                        # Keep all synthetic dates inside the dataset's
                        # observed recent window (2025 through September 2026).
                        year = 2025 + (i % 2)
                        month = (i % 9) + 1
                        day = (i % 27) + 1
                        date = f"{year}-{month:02d}-{day:02d}"
                        generation_style = "recent_dated_issue_repetition"
                        repetition_group = f"{scenario_id}_recent_issue"

                    # Store provenance on every injected row. Downstream tools
                    # must treat is_synthetic=True as an experimental label,
                    # never as a genuine Airbnb guest review.
                    rows.append(
                        {
                            "synthetic_review_id": synthetic_id,
                            "scenario_id": scenario_id,
                            "listing_id": listing_id,
                            "listing_name": listing_name,
                            "attack_type": attack_type,
                            "attack_variant": attack_variant,
                            "intensity": intensity,
                            "synthetic_index": i + 1,
                            "review_date": date,
                            "text": text,
                            "target_aspect": aspect,
                            "sentiment": sentiment,
                            "target_issue": issue,
                            "generation_style": generation_style,
                            "repetition_group": repetition_group,
                            "is_synthetic": True,
                            "source_status": "synthetic_test_stimulus_not_guest_feedback",
                            "generation_seed": SEED,
                        }
                    )

    # Return in the same order expected by main(): review rows, scenario
    # manifest, then the target-selection audit trail.
    return pd.DataFrame(rows), pd.DataFrame(scenario_rows), pd.DataFrame(target_rows)


def add_baseline_scenarios(representative, challenge, manifest):
    """Create two no-attack reference conditions for each listing.

    baseline_rep_only contains the representative genuine reviews.
    baseline_with_challenge adds the genuine challenge reviews. The latter
    is the direct comparison for every attacked scenario, because attacks
    begin with that same representative-plus-challenge input.

    The manifest parameter is retained for compatibility with the original
    function signature but is not used inside this function.
    """
    rows = []
    listing_names = (
        representative.drop_duplicates("listing_id")
        .set_index("listing_id")["listing_name"]
        .to_dict()
    )
    baseline_rows = []
    for listing_id, listing_name in listing_names.items():
        # Build the two baselines separately so the analysis can distinguish
        # a change caused by adding genuine challenge evidence from a change
        # caused by adding fabricated reviews.
        for baseline_type, include_challenge in [
            ("baseline_rep_only", False),
            ("baseline_with_challenge", True),
        ]:
            scenario_id = f"{int(listing_id)}_{baseline_type}"
            base = representative[representative["listing_id"] == listing_id].copy()
            base["review_set"] = "representative"
            if include_challenge:
                extra = challenge[challenge["listing_id"] == listing_id].copy()
                extra["review_set"] = "challenge"
                base = pd.concat([base, extra], ignore_index=True)
            # Copy each genuine review into a scenario-specific input row.
            # No synthetic reviews appear in either baseline.
            for _, review in base.iterrows():
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "listing_id": int(listing_id),
                        "listing_name": listing_name,
                        "review_id": str(review["id"]),
                        "review_date": str(review["date"]),
                        "text": str(review["comments"]),
                        "review_set": review["review_set"],
                        "attack_type": "none",
                        "attack_variant": "none",
                        "intensity": "baseline",
                        "is_synthetic": False,
                        "target_aspect": "",
                        "sentiment": "",
                        "target_issue": "",
                    }
                )
            # Keep a matching manifest row for the baseline, including the
            # exact source set used and synthetic_review_count=0.
            baseline_rows.append(
                {
                    "scenario_id": scenario_id,
                    "listing_id": int(listing_id),
                    "listing_name": listing_name,
                    "scenario_type": "baseline",
                    "attack_type": "none",
                    "attack_variant": "none",
                    "intensity": "baseline",
                    "synthetic_review_count": 0,
                    "base_input": (
                        "100 representative reviews"
                        if not include_challenge
                        else "100 representative + all listing challenge reviews"
                    ),
                    "target_aspect": "",
                    "target_issue": "",
                    "attack_objective": "Reference condition with no synthetic reviews.",
                    "expected_failure": "No attack-specific failure expected.",
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(baseline_rows)


def main():
    """Assemble the experiment inputs, validate them, and write output CSVs.

    Only files under data/adversarial/ are written. Re-running this script
    replaces those generated CSVs, so do not rerun it after manually editing
    scenario inputs or after changing the experimental design unintentionally.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Step 1: Load genuine reviews and benchmark annotations.
    representative, challenge, prevalence, minority = load_inputs()

    # Step 2: Construct the fabricated review bank and attack metadata.
    synthetic, attack_manifest, targets = build_synthetic_reviews(prevalence, minority)
    # Step 3: Construct the two genuine-only reference conditions per listing.
    baseline_inputs, baseline_manifest = add_baseline_scenarios(
        representative, challenge, attack_manifest
    )

    # Each attack scenario starts from the same representative-plus-challenge
    # baseline for its listing. Only the synthetic additions vary by scenario.
    # Begin with the baseline input rows, then append each attacked input.
    # Each attacked input includes all genuine representative/challenge rows
    # PLUS only the synthetic reviews belonging to that one scenario.
    scenario_inputs = [baseline_inputs]
    # Step 4: Materialize the complete review corpus for every attack.
    # Repeating genuine rows across scenarios is intentional: it makes each
    # scenario_inputs.csv subset self-contained for downstream summarization.
    for _, scenario in attack_manifest.iterrows():
        listing_id = int(scenario["listing_id"])
        base = representative[representative["listing_id"] == listing_id].copy()
        base["review_set"] = "representative"
        extra = challenge[challenge["listing_id"] == listing_id].copy()
        extra["review_set"] = "challenge"
        base = pd.concat([base, extra], ignore_index=True)

        for _, review in base.iterrows():
            scenario_inputs.append(
                pd.DataFrame(
                    [
                        {
                            "scenario_id": scenario["scenario_id"],
                            "listing_id": listing_id,
                            "listing_name": scenario["listing_name"],
                            "review_id": str(review["id"]),
                            "review_date": str(review["date"]),
                            "text": str(review["comments"]),
                            "review_set": review["review_set"],
                            "attack_type": scenario["attack_type"],
                            "intensity": scenario["intensity"],
                            "is_synthetic": False,
                            "target_aspect": "",
                            "sentiment": "",
                            "target_issue": "",
                        }
                    ]
                )
            )

        # Append only this scenario's fabricated reviews; provenance is kept
        # through review_set="synthetic" and is_synthetic=True.
        injected = synthetic[synthetic["scenario_id"] == scenario["scenario_id"]]
        scenario_inputs.append(
            pd.DataFrame(
                [
                    {
                        "scenario_id": scenario["scenario_id"],
                        "listing_id": listing_id,
                        "listing_name": scenario["listing_name"],
                        "review_id": row["synthetic_review_id"],
                        "review_date": row["review_date"],
                        "text": row["text"],
                        "review_set": "synthetic",
                        "attack_type": row["attack_type"],
                        "attack_variant": row["attack_variant"],
                        "intensity": row["intensity"],
                        "is_synthetic": True,
                        "target_aspect": row["target_aspect"],
                        "sentiment": row["sentiment"],
                        "target_issue": row["target_issue"],
                    }
                    for _, row in injected.iterrows()
                ]
            )
        )

    # Combine baseline and attack definitions into a single scenario manifest,
    # and combine their individual review rows into one input CSV.
    manifest = pd.concat([baseline_manifest, attack_manifest], ignore_index=True)
    inputs = pd.concat(scenario_inputs, ignore_index=True)

    # Confirm that each suppression variant uses the same number of reviews
    # at every listing and intensity. The difference should be wording, not size.
    paired = attack_manifest[attack_manifest["attack_type"] == "minority_suppression"]
    paired_counts = paired.groupby(["listing_id", "intensity"])[
        "synthetic_review_count"
    ]
    if (
        not (paired_counts.nunique() == 1).all()
        or not (paired_counts.size() == 2).all()
    ):
        raise ValueError("Suppression variants must have paired review counts.")

    # Basic checks prevent synthetic rows from leaking into the original sample
    # and ensure every attack scenario has the requested number of injected rows.
    if synthetic["synthetic_review_id"].duplicated().any():
        raise ValueError("Synthetic review IDs are not unique.")
    if not synthetic["is_synthetic"].all():
        raise ValueError("Synthetic review flag is missing.")
    injected_counts = synthetic.groupby("scenario_id").size()
    expected_counts = manifest[manifest["scenario_type"] == "attack"].set_index(
        "scenario_id"
    )["synthetic_review_count"]
    if not injected_counts.equals(expected_counts.sort_index()):
        raise ValueError("Synthetic review counts do not match the scenario manifest.")

    # Step 5: Write the experiment's generated datasets. index=False avoids
    # exporting pandas' row index as a meaningless extra CSV column.
    # These are derived files, not modifications to the source reviews.
    synthetic.to_csv(OUTPUT_DIR / "synthetic_reviews.csv", index=False)
    manifest.to_csv(OUTPUT_DIR / "scenario_manifest.csv", index=False)
    targets.to_csv(OUTPUT_DIR / "attack_target_selection.csv", index=False)
    inputs.to_csv(OUTPUT_DIR / "scenario_inputs.csv", index=False)

    # Keep a compact count table alongside the detailed manifest for quick
    # inspection before selecting scenarios for a summarization run.
    # Summarize the design into counts by scenario type, attack family,
    # variant, and intensity. This is a quick completeness check; it is NOT
    # an outcome or attack-success evaluation.
    overview = (
        manifest.groupby(
            ["scenario_type", "attack_type", "attack_variant", "intensity"],
            dropna=False,
        )
        .agg(
            scenarios=("scenario_id", "count"),
            synthetic_reviews=("synthetic_review_count", "sum"),
        )
        .reset_index()
    )
    overview.to_csv(OUTPUT_DIR / "scenario_overview.csv", index=False)

    print("Attack scenarios created.")
    print(f"Scenarios: {len(manifest)}")
    print(f"Synthetic reviews: {len(synthetic)}")
    print(f"Scenario input rows: {len(inputs)}")
    print(f"Files saved to: {OUTPUT_DIR.resolve()}")


# Run main() only when this file is executed as a script. Importing it from
# another Python module will not automatically regenerate scenario files.
if __name__ == "__main__":
    main()
