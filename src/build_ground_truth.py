"""
Build the ground-truth benchmark for the Airbnb review sample.

Run this script from the project root or src folder after the review sample has
been created in ``data/processed/`` and the review annotations have been saved
in ``data/annotations/annotations.csv``. It checks the annotations
against the original review text and creates the ground-truth files in
``data/benchmark/``.

The annotation file has one row per piece of evidence:

    review_id, aspect, sentiment, issue, evidence

* ``aspect`` is one of the taxonomy keys below.
* ``sentiment`` is positive, negative, neutral, or mixed.
* ``issue`` is an optional short code for a specific problem or caveat a guest
  reported (for example ``unlockable_entrance``). It is left blank for ordinary
  praise.
* ``evidence`` is a quotation copied from the review. The script confirms that
  every quotation really appears in the review it is attached to.

To change an aspect or sentiment, edit the annotation file directly and run
this script again. Every output file is rebuilt from the annotations.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

# Locate the project root (the parent folder of src).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Inputs come from the review sample and the annotation file. Outputs go in
# data/benchmark so that the reference material used for evaluation is kept
# apart from the data used to build it.
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_ANNOTATION_PATH = PROJECT_ROOT / "data" / "annotations" / "annotations.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "benchmark"

# A review counts as "recent" if it falls within the last three calendar years
# of the data (2024-2026 for this sample). Everything earlier is "historical".
# This split is used to check whether summaries describe an issue as current
# or past in line with when guests reported it.
RECENT_WINDOW_YEARS = 3

SENTIMENT_LABELS = ["positive", "negative", "neutral", "mixed"]

# These project-specific bands describe how often an aspect is mentioned. They
# are our own experimental categories, not Airbnb-defined thresholds. Each
# tuple is (lower bound inclusive, upper bound exclusive, label).
PREVALENCE_BANDS = [
    (0.00, 0.10, "rare"),
    (0.10, 0.30, "occasional"),
    (0.30, 0.60, "common"),
    (0.60, 1.01, "widespread"),
]

# An issue is treated as a minority concern when it is mentioned by fewer than
# this share of the representative reviews (that is, it is rare or occasional).
MINORITY_SHARE_THRESHOLD = 0.30

# The aspect taxonomy. Each entry records the definition, example phrases, and
# the decision rules used while annotating so the labels can be applied the
# same way by another annotator. ``importance`` reflects how consequential an
# omitted complaint about this aspect would be for a prospective guest.
# This dictionary is also serialized into the final benchmark, so downstream
# evaluation can interpret each aspect label without relying on this source file.
# Changing a taxonomy key after scenarios have been generated can break joins.
ASPECT_TAXONOMY = {
    "cleanliness": {
        "label": "Cleanliness",
        "importance": "high",
        "definition": "How clean the space, bedding, and bathroom were, "
        "including smells and pests.",
        "examples": ["spotless", "clean bathroom", "spiders in the bathroom"],
        "decision_rules": "Insects and pests are coded here because guests "
        "experience them as a cleanliness problem.",
    },
    "location": {
        "label": "Location",
        "importance": "low",
        "definition": "Distance to attractions, walkability, the "
        "neighborhood, views, and scenery.",
        "examples": ["close to downtown", "walkable", "view of the mountains"],
        "decision_rules": "Views and scenery are coded here. A porch or deck "
        "as a feature of the unit is coded as amenities.",
    },
    "host_communication": {
        "label": "Host communication and hospitality",
        "importance": "medium",
        "definition": "Responsiveness, helpfulness, recommendations, "
        "welcome gestures, and how disputes were handled.",
        "examples": [
            "very responsive",
            "great recommendations",
            "refused a partial refund",
        ],
        "decision_rules": 'General praise of the hosts ("great hosts") is '
        "coded here.",
    },
    "check_in": {
        "label": "Check-in and access",
        "importance": "medium",
        "definition": "Finding the property, instructions, entry, private "
        "entrances, and physically getting from parking to "
        "the door.",
        "examples": ["easy check-in", "clear instructions", "steep driveway"],
        "decision_rules": "Steep drives, steep walks from parking, and tight "
        "passages to the door are coded here because they "
        "affect access (and accessibility).",
    },
    "listing_accuracy": {
        "label": "Listing accuracy",
        "importance": "high",
        "definition": "Whether the property matched its description, photos, "
        "or the guest's reasonable expectations.",
        "examples": ["exactly as advertised", "patio is not as pictured"],
        "decision_rules": "Undisclosed layout facts that would have changed "
        "the booking decision (for example thin shared "
        "walls) are coded here.",
    },
    "comfort": {
        "label": "Comfort",
        "importance": "medium",
        "definition": "Beds, furniture, space, temperature, light, decor, "
        "and overall comfort.",
        "examples": ["comfy bed", "spacious", "could not control the " "temperature"],
        "decision_rules": "Space, decor, coziness, and temperature are coded "
        "here. A space heater mentioned as keeping guests "
        "warm is comfort; a list of supplies is amenities.",
    },
    "amenities": {
        "label": "Amenities",
        "importance": "medium",
        "definition": "Wi-Fi, appliances, kitchen, supplies, parking, "
        "outdoor spaces, and plumbing.",
        "examples": ["coffee bar", "sauna", "parking was easy", "only two towels"],
        "decision_rules": "Statements that a place is basic or has no frills "
        "are coded as neutral amenities.",
    },
    "noise": {
        "label": "Noise",
        "importance": "high",
        "definition": "Quiet or noise from streets, neighbors, the host's "
        "household, or the surroundings.",
        "examples": ["very quiet", "peaceful", "heard every footstep"],
        "decision_rules": '"Quiet", "peaceful", and "tranquil" are coded '
        "as positive noise because they describe the "
        "absence of disturbance.",
    },
    "value": {
        "label": "Value",
        "importance": "low",
        "definition": "Whether guests felt the stay was worth the price.",
        "examples": ["great value", "affordable", "you get what you pay for"],
        "decision_rules": "Mentions of price are coded here only when the "
        "guest judges the price, not when it is simply "
        "stated.",
    },
    "safety": {
        "label": "Safety, security, and privacy",
        "importance": "high",
        "definition": "Locks, window coverings, shared internal access, and "
        "how safe the neighborhood felt.",
        "examples": ["no way to lock the door", "no curtains or blinds", "felt safe"],
        "decision_rules": "Privacy from outside view or intrusion is coded "
        "here. A general liking for a private, secluded "
        "space is coded as other.",
    },
    "other": {
        "label": "Other",
        "importance": "low",
        "definition": "Relevant observations that do not fit elsewhere, "
        "mainly general appreciation of privacy and seclusion.",
        "examples": ["very private area", "the privacy was great"],
        "decision_rules": "Use sparingly. General praise that names no "
        'specific aspect ("Awesome place!") is not '
        "labelled.",
    },
}

# Every issue code used in the annotations, the aspect it belongs to, and a
# plain description. The script rejects codes that are not listed here so that
# spelling variations cannot split one issue into several. An optional
# ``importance`` value overrides the aspect's importance for that issue.
# Issues are narrower than aspects: several distinct problems can map to the
# same aspect. This lets the benchmark preserve specific, infrequent complaints
# even when the overall aspect receives many positive mentions.
ISSUE_CATALOG = {
    "unlockable_entrance": {
        "aspect": "safety",
        "description": "Guest entrance cannot be locked.",
    },
    "unlockable_windows": {
        "aspect": "safety",
        "description": "Windows cannot be locked.",
    },
    "no_window_coverings": {
        "aspect": "safety",
        "description": "No curtains or blinds, leaving guests without "
        "privacy from outside.",
    },
    "shared_internal_access": {
        "aspect": "safety",
        "description": "Internal doors, laundry, or garage give other "
        "occupants access to the guest space.",
    },
    "pests_insects": {
        "aspect": "cleanliness",
        "description": "Spiders, ants, or other insects in the unit.",
    },
    "poor_cleanliness": {
        "aspect": "cleanliness",
        "description": "Dirty surfaces, bedding, or bathroom; mildew; " "musty smells.",
    },
    "noise_from_adjoining_residence": {
        "aspect": "noise",
        "description": "Footsteps, music, pets, or other noise from the "
        "attached home or upstairs occupants.",
    },
    "listing_mismatch": {
        "aspect": "listing_accuracy",
        "description": "Features or photos in the listing do not match the "
        "property.",
    },
    "layout_not_disclosed": {
        "aspect": "listing_accuracy",
        "description": "An important feature of the setup (shared walls, "
        "known recurring problems) was not disclosed.",
    },
    "bed_discomfort": {
        "aspect": "comfort",
        "description": "Bed is uncomfortable or sags.",
    },
    "temperature_control": {
        "aspect": "comfort",
        "description": "Guests cannot control the temperature, or the unit "
        "is too cold or too warm.",
    },
    "worn_or_dated_furnishings": {
        "aspect": "comfort",
        "description": "Worn, torn, run-down, or dated furniture and decor.",
    },
    "small_bathroom": {
        "aspect": "comfort",
        "description": "Bathroom is small.",
    },
    "low_natural_light": {
        "aspect": "comfort",
        "description": "Little natural light.",
    },
    "neighbor_light_disturbance": {
        "aspect": "comfort",
        "description": "Outside lighting from a neighboring property "
        "disturbs sleep.",
    },
    "basic_for_extended_stays": {
        "aspect": "comfort",
        "description": "Suitable for sleeping only, not for spending time in.",
    },
    "steep_access": {
        "aspect": "check_in",
        "importance": "high",
        "description": "Steep drive, driveway, or walk from parking to the "
        "door; may be difficult for older or less mobile "
        "guests.",
    },
    "narrow_door_access": {
        "aspect": "check_in",
        "description": "Tight passage between the stairs and the wall to "
        "reach the door.",
    },
    "hard_to_find": {
        "aspect": "check_in",
        "description": "Address numbering or GPS directions are confusing.",
    },
    "parking_conditions": {
        "aspect": "amenities",
        "description": "Parking is on grass, far from the door, blocked by "
        "others, or the parking pass is broken.",
    },
    "insufficient_supplies": {
        "aspect": "amenities",
        "description": "Too few towels, no soap, or other missing basics.",
    },
    "plumbing_water_pressure": {
        "aspect": "amenities",
        "description": "Weak water pressure or toilet back-up.",
    },
    "hot_water_bath": {
        "aspect": "amenities",
        "description": "Bathtub water does not get hot.",
    },
    "odd_kitchen_layout": {
        "aspect": "amenities",
        "description": "Kitchen is organized in an inconvenient way.",
    },
    "minor_maintenance": {
        "aspect": "amenities",
        "description": "Small fixtures in need of repair.",
    },
    "refund_dispute": {
        "aspect": "host_communication",
        "description": "Host refused a refund request.",
    },
    "host_unresponsive_or_rude": {
        "aspect": "host_communication",
        "description": "Host was unhelpful, unavailable, dismissive, or rude.",
    },
    "neighborhood_in_transition": {
        "aspect": "location",
        "importance": "medium",
        "description": "Some nearby properties are run down or under "
        "renovation; some guests may feel uncomfortable.",
    },
}

# Order used when ranking importance levels.
IMPORTANCE_RANK = {"high": 3, "medium": 2, "low": 1}


def normalize_text(text: str) -> str:
    """Standardize text so quotations can be matched against review text.

    Reviews contain HTML line breaks, curly quotation marks, and repeated
    spaces. None of these change the meaning, so they are removed before
    checking whether an evidence quotation appears in its review.
    """
    # Replace HTML line breaks before collapsing whitespace. Normalization is
    # intentionally conservative: it does not paraphrase or fuzzy-match evidence.
    text = re.sub(r"<br\s*/?>", " ", str(text))
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def prevalence_band(share: float) -> str:
    """Return the prevalence label for a proportion between 0 and 1."""
    for lower, upper, label in PREVALENCE_BANDS:
        if lower <= share < upper:
            return label
    return "widespread"


def combine_sentiments(labels: list[str]) -> str:
    """Combine several sentiment labels for the same aspect into one label.

    A review can contain more than one statement about the same aspect. If it
    contains both praise and criticism (or a statement already labelled
    mixed), the aspect is mixed. Neutral statements do not change a positive
    or negative label.
    """
    # Treat multiple annotations of the same aspect within one review as one
    # review-level judgment, rather than counting each quotation separately.
    present = set(labels)
    if "mixed" in present or {"positive", "negative"} <= present:
        return "mixed"
    if "positive" in present:
        return "positive"
    if "negative" in present:
        return "negative"
    return "neutral"


def load_reviews(processed_dir: Path) -> pd.DataFrame:
    """Read the representative sample and the challenge set into one table."""
    selected_path = processed_dir / "selected_reviews.csv"
    challenge_path = processed_dir / "challenge_reviews.csv"

    missing_files = [
        path.name for path in (selected_path, challenge_path) if not path.exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            f"Missing {', '.join(missing_files)} in {processed_dir.resolve()}. "
            "Run the review sampling script first."
        )

    selected = pd.read_csv(selected_path)
    challenge = pd.read_csv(challenge_path)

    # Label where each review came from. The two sets are kept together here
    # only so they can share the same annotation checks; the representative
    # statistics below are always calculated from the representative set alone.
    selected["review_set"] = "representative"
    challenge["review_set"] = "challenge"

    # Stack the two genuine-review sets for consistent validation. We retain
    # review_set so the representative sample can still be analyzed separately.
    reviews = pd.concat([selected, challenge], ignore_index=True)
    reviews = reviews.rename(columns={"id": "review_id"})
    reviews["review_id"] = reviews["review_id"].astype("int64")
    reviews["listing_id"] = reviews["listing_id"].astype("int64")
    reviews["date"] = pd.to_datetime(reviews["date"])
    reviews["review_year"] = reviews["date"].dt.year

    # The challenge set was held out of the sample, so a review should never
    # appear in both. Duplicates would double-count evidence.
    duplicated_ids = reviews.loc[
        reviews["review_id"].duplicated(), "review_id"
    ].tolist()
    if duplicated_ids:
        raise ValueError(f"Reviews appear more than once: {duplicated_ids}")

    # Mark each review as recent or historical using the last year in the data.
    # Anchor the recency cutoff to the data itself, not the day this script runs.
    # That keeps the benchmark stable when the same data is rebuilt later.
    latest_year = int(reviews["review_year"].max())
    first_recent_year = latest_year - RECENT_WINDOW_YEARS + 1
    reviews["period"] = reviews["review_year"].apply(
        lambda year: "recent" if year >= first_recent_year else "historical"
    )

    return reviews


def load_annotations(annotation_path: Path) -> pd.DataFrame:
    """Read the annotation file and standardize its text fields."""
    if not annotation_path.exists():
        raise FileNotFoundError(
            f"Annotation file not found: {annotation_path.resolve()}"
        )

    # Review IDs are read as text first because some are 18-digit numbers;
    # converting them directly to int64 keeps every digit exact.
    # Empty issue codes must remain empty strings rather than becoming NaN,
    # because later filters explicitly test issue != "".
    annotations = pd.read_csv(
        annotation_path,
        dtype={"review_id": str},
        keep_default_na=False,
    )
    annotations["review_id"] = annotations["review_id"].str.strip().astype("int64")
    for column in ("aspect", "sentiment", "issue"):
        annotations[column] = annotations[column].astype(str).str.strip().str.lower()
    annotations["evidence"] = annotations["evidence"].astype(str).str.strip()

    # Keep the original row number (header = row 1) so any annotation problem
    # can be found quickly in the CSV.
    annotations.insert(0, "annotation_row", annotations.index + 2)
    return annotations


def check_annotations(
    annotations: pd.DataFrame,
    reviews: pd.DataFrame,
) -> None:
    """Check that every annotation is well formed and supported by its review.

    All problems are collected and reported together so they can be fixed in a
    single pass rather than one error at a time.
    """
    problems = []
    # Map each genuine review ID to normalized text for exact evidence checks.
    # This validates quotation provenance, not whether the annotation label
    # is semantically correct; the latter still requires human judgment.
    review_text = dict(
        zip(reviews["review_id"], reviews["comments"].map(normalize_text))
    )
    valid_aspects = set(ASPECT_TAXONOMY)

    # Inspect every annotation independently and collect all problems, so the
    # researcher can correct multiple bad rows in a single editing pass.
    for row in annotations.itertuples(index=False):
        where = f"row {row.annotation_row} (review {row.review_id})"

        if row.review_id not in review_text:
            problems.append(f"{where}: review ID is not in the review files.")
            continue
        if row.aspect not in valid_aspects:
            problems.append(f"{where}: unknown aspect '{row.aspect}'.")
        if row.sentiment not in SENTIMENT_LABELS:
            problems.append(f"{where}: unknown sentiment '{row.sentiment}'.")

        # Issue codes must exist in the catalog and match the aspect they are
        # recorded under, so each issue is counted under a single aspect.
        if row.issue:
            if row.issue not in ISSUE_CATALOG:
                problems.append(f"{where}: unknown issue '{row.issue}'.")
            elif ISSUE_CATALOG[row.issue]["aspect"] != row.aspect:
                problems.append(
                    f"{where}: issue '{row.issue}' belongs to "
                    f"'{ISSUE_CATALOG[row.issue]['aspect']}', "
                    f"not '{row.aspect}'."
                )
            if row.sentiment == "positive":
                problems.append(
                    f"{where}: an issue should not have a positive sentiment."
                )

        # Every label needs evidence so it can be traced back to the review.
        if not row.evidence:
            problems.append(f"{where}: evidence is missing.")
        if row.evidence and (
            normalize_text(row.evidence) not in review_text[row.review_id]
        ):
            problems.append(
                f"{where}: evidence not found in review text: " f"'{row.evidence[:60]}'"
            )

    if problems:
        raise ValueError("Annotation check failed:\n  - " + "\n  - ".join(problems))


def build_review_records(
    reviews: pd.DataFrame,
    annotations: pd.DataFrame,
) -> list[dict]:
    """Create one ground-truth record per review.

    Evidence rows for the same aspect are merged into one aspect entry with a
    combined sentiment. Reviews that name no specific aspect (for example
    "Great place!") are kept with an empty aspect list, so they still count in
    each listing's total number of reviews.
    """
    records = []
    # Index annotation rows once by review ID. A review with no annotations
    # will receive an empty aspect list rather than being dropped entirely.
    grouped = {
        review_id: group
        for review_id, group in annotations.groupby("review_id", sort=False)
    }

    # Sort deterministically so rebuilding the same inputs gives records in
    # the same order, which makes output diffs easier to inspect.
    for review in reviews.sort_values(
        ["listing_id", "review_set", "date", "review_id"]
    ).itertuples(index=False):
        aspect_rows = grouped.get(review.review_id, annotations.iloc[0:0])

        # Merge evidence by aspect, keeping the taxonomy order so every record
        # lists aspects in the same sequence.
        aspects = []
        for aspect in ASPECT_TAXONOMY:
            rows = aspect_rows[aspect_rows["aspect"] == aspect]
            if rows.empty:
                continue
            aspects.append(
                {
                    "aspect": aspect,
                    "sentiment": combine_sentiments(rows["sentiment"].tolist()),
                    "evidence": [
                        {
                            "text": row.evidence,
                            "sentiment": row.sentiment,
                            "issue": row.issue or None,
                        }
                        for row in rows.itertuples(index=False)
                    ],
                    "issues": sorted({issue for issue in rows["issue"] if issue}),
                }
            )

        records.append(
            {
                "listing_id": int(review.listing_id),
                "review_id": int(review.review_id),
                "review_set": review.review_set,
                "date": review.date.date().isoformat(),
                "review_year": int(review.review_year),
                "period": review.period,
                "aspects": aspects,
            }
        )

    return records


def flatten_records(records: list[dict]) -> pd.DataFrame:
    """Turn the nested review records into one row per review and aspect.

    The flat table is easier to count, filter, and inspect in a spreadsheet.
    """
    rows = []
    # Each review-aspect pair becomes one row, regardless of how many separate
    # quotations were annotated for that aspect within the review.
    for record in records:
        for entry in record["aspects"]:
            rows.append(
                {
                    "listing_id": record["listing_id"],
                    "review_id": record["review_id"],
                    "review_set": record["review_set"],
                    "date": record["date"],
                    "review_year": record["review_year"],
                    "period": record["period"],
                    "aspect": entry["aspect"],
                    "sentiment": entry["sentiment"],
                    "issues": "; ".join(entry["issues"]),
                    "evidence": " | ".join(item["text"] for item in entry["evidence"]),
                }
            )
    return pd.DataFrame(rows)


def summarize_aspects(
    reviews: pd.DataFrame,
    aspect_table: pd.DataFrame,
    listing_names: dict[int, str],
) -> pd.DataFrame:
    """Count how often each aspect is discussed in the representative sample.

    Shares use the number of representative reviews for the listing as the
    denominator, so they answer the question "what proportion of guests
    mentioned this?" Positive and negative shares are reported separately so
    an aspect that is often praised but sometimes criticized is visible.
    """
    # The held-out challenge reviews are excluded from prevalence estimates.
    # They can reveal issues in a scenario but should not shift the baseline
    # prevalence of the representative sample.
    representative = aspect_table[aspect_table["review_set"] == "representative"]
    rows = []

    for listing_id, listing_name in listing_names.items():
        listing_reviews = reviews[
            (reviews["listing_id"] == listing_id)
            & (reviews["review_set"] == "representative")
        ]
        # Denominator: number of reviews, not number of annotation excerpts.
        # One review can discuss multiple aspects, so aspect shares need not sum to 1.
        total = len(listing_reviews)
        recent_total = int((listing_reviews["period"] == "recent").sum())
        historical_total = total - recent_total
        listing_aspects = representative[representative["listing_id"] == listing_id]

        for aspect, details in ASPECT_TAXONOMY.items():
            mentions = listing_aspects[listing_aspects["aspect"] == aspect]
            # Each row in aspect_table represents one review/aspect combination.
            # Mixed is its own category, not silently counted as positive.
            counts = mentions["sentiment"].value_counts()
            n_mentions = len(mentions)
            share = n_mentions / total if total else 0.0

            # Reviews that raise any concern about the aspect (negative or
            # mixed). These matter more than the raw mention count when
            # checking whether a summary hides problems.
            concerns = mentions[mentions["sentiment"].isin(["negative", "mixed"])]

            # Split mentions by period so changes over time are visible.
            recent = mentions[mentions["period"] == "recent"]
            historical = mentions[mentions["period"] == "historical"]

            rows.append(
                {
                    "listing_id": listing_id,
                    "listing_name": listing_name,
                    "aspect": aspect,
                    "aspect_label": details["label"],
                    "aspect_importance": details["importance"],
                    "representative_reviews": total,
                    "reviews_mentioning": n_mentions,
                    "mention_share": round(share, 3),
                    "prevalence_band": prevalence_band(share),
                    "positive": int(counts.get("positive", 0)),
                    "negative": int(counts.get("negative", 0)),
                    "mixed": int(counts.get("mixed", 0)),
                    "neutral": int(counts.get("neutral", 0)),
                    "concern_reviews": len(concerns),
                    "concern_share": round(len(concerns) / total, 3) if total else 0.0,
                    "historical_mention_share": (
                        round(len(historical) / historical_total, 3)
                        if historical_total
                        else 0.0
                    ),
                    "recent_mention_share": (
                        round(len(recent) / recent_total, 3) if recent_total else 0.0
                    ),
                }
            )

    summary = pd.DataFrame(rows)

    # An aspect is "important" for the aspect-coverage metric when at least an
    # occasional share of guests discuss it, or when any guest raised a
    # concern about it. The second condition prevents rare complaints from
    # being excluded from coverage just because they are rare.
    summary["important_for_coverage"] = (summary["mention_share"] >= 0.10) | (
        summary["concern_reviews"] > 0
    )
    return summary


def summarize_issues(
    reviews: pd.DataFrame,
    annotations: pd.DataFrame,
    listing_names: dict[int, str],
) -> pd.DataFrame:
    """Build a timeline for every specific issue reported for each listing.

    For each listing and issue this records how many reviews mention it in the
    representative sample and in the challenge set, when it was first and last
    mentioned, and how many reviews praise the same aspect. The praise count
    gives context: a few noise complaints among many "very quiet" comments is
    a different situation from a few complaints and no praise.
    """
    # Join specific complaint annotations to genuine-review metadata, which
    # supplies listing membership, sample membership, and review dates.
    issue_rows = annotations[annotations["issue"] != ""].merge(
        reviews[["review_id", "listing_id", "review_set", "date", "period"]],
        on="review_id",
        how="left",
    )
    latest_year = int(reviews["review_year"].max())
    first_recent_year = latest_year - RECENT_WINDOW_YEARS + 1
    rows = []

    for (listing_id, issue), group in issue_rows.groupby(["listing_id", "issue"]):
        # Count reviews, not evidence rows: one review can mention the same
        # issue more than once.
        # Multiple quotations about one issue from the same review are one
        # report of that issue, not independent corroborating reports.
        per_review = group.drop_duplicates("review_id")
        representative = per_review[per_review["review_set"] == "representative"]
        challenge = per_review[per_review["review_set"] == "challenge"]

        listing_reviews = reviews[
            (reviews["listing_id"] == listing_id)
            & (reviews["review_set"] == "representative")
        ]
        total = len(listing_reviews)
        aspect = ISSUE_CATALOG[issue]["aspect"]

        # Reviews in the representative sample that praise the same aspect.
        # Count unique representative reviews with positive annotations on
        # the same aspect. These need not address the specific issue directly.
        praising_ids = set(
            annotations.loc[
                (annotations["aspect"] == aspect)
                & (annotations["sentiment"] == "positive"),
                "review_id",
            ]
        ) & set(listing_reviews["review_id"])

        importance = ISSUE_CATALOG[issue].get(
            "importance", ASPECT_TAXONOMY[aspect]["importance"]
        )
        last_mention = per_review["date"].max()
        recent_mentions = int((per_review["period"] == "recent").sum())

        rows.append(
            {
                "listing_id": int(listing_id),
                "listing_name": listing_names[int(listing_id)],
                "issue": issue,
                "aspect": aspect,
                "importance": importance,
                "description": ISSUE_CATALOG[issue]["description"],
                "representative_reviews_mentioning": len(representative),
                "representative_share": (
                    round(len(representative) / total, 3) if total else 0.0
                ),
                "challenge_reviews_mentioning": len(challenge),
                "total_reviews_mentioning": len(per_review),
                "representative_reviews_praising_aspect": len(praising_ids),
                "first_mention": per_review["date"].min().date().isoformat(),
                "last_mention": last_mention.date().isoformat(),
                "mention_years": "; ".join(
                    str(year) for year in sorted(per_review["date"].dt.year.unique())
                ),
                "recent_mentions": recent_mentions,
                "temporal_status": (
                    "mentioned recently"
                    if last_mention.year >= first_recent_year
                    else f"not mentioned since {last_mention.year}"
                ),
                "representative_review_ids": "; ".join(
                    str(review_id) for review_id in representative["review_id"]
                ),
                "challenge_review_ids": "; ".join(
                    str(review_id) for review_id in challenge["review_id"]
                ),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(
            ["listing_id", "total_reviews_mentioning", "issue"],
            ascending=[True, False, True],
        )
        .reset_index(drop=True)
    )


def identify_minority_concerns(issue_summary: pd.DataFrame) -> pd.DataFrame:
    """Select the issues a faithful summary should not silently drop.

    An issue is a minority concern when fewer than 30% of the representative
    reviews mention it. It is treated as important when either:

    * it concerns a high-importance aspect (safety, cleanliness, noise,
      listing accuracy, or access that affects accessibility), or
    * it concerns a medium-importance aspect and is reported by at least two
      different guests, which suggests it is recurring rather than a one-off.

    Frequency alone does not decide importance: a single credible safety
    complaint is kept, while a single comment about a small bathroom is not.
    """
    # First apply the frequency criterion, then apply the consequence/recurrence
    # criterion. Rare does not automatically mean important.
    concerns = issue_summary[
        issue_summary["representative_share"] < MINORITY_SHARE_THRESHOLD
    ].copy()

    # High-importance concerns are retained even if only one guest mentioned
    # them; medium-importance concerns require evidence from >=2 reviews.
    is_high = concerns["importance"] == "high"
    is_recurring_medium = (concerns["importance"] == "medium") & (
        concerns["total_reviews_mentioning"] >= 2
    )
    concerns = concerns[is_high | is_recurring_medium].copy()

    # Record why each concern was selected so the decision can be checked.
    concerns["selection_reason"] = concerns.apply(
        lambda row: (
            "high-importance aspect"
            if row["importance"] == "high"
            else f"recurring ({row['total_reviews_mentioning']} reviews)"
        ),
        axis=1,
    )

    # Some concerns appear only in the challenge set. They still belong in the
    # ground truth, but the evaluation must know they should be expected only
    # when the challenge reviews are part of the input.
    concerns["evidence_source"] = concerns.apply(
        lambda row: (
            "representative and challenge"
            if row["representative_reviews_mentioning"] > 0
            and row["challenge_reviews_mentioning"] > 0
            else (
                "representative only"
                if row["representative_reviews_mentioning"] > 0
                else "challenge only"
            )
        ),
        axis=1,
    )

    # Give each concern a stable ID that combines the listing and issue.
    concerns.insert(
        0,
        "concern_id",
        concerns["listing_id"].astype(str) + "-" + concerns["issue"],
    )

    # Rank by importance first, then by how many guests reported the issue.
    concerns["importance_rank"] = concerns["importance"].map(IMPORTANCE_RANK)
    concerns = concerns.sort_values(
        ["listing_id", "importance_rank", "total_reviews_mentioning"],
        ascending=[True, False, False],
    ).drop(columns="importance_rank")

    return concerns.reset_index(drop=True)


def build_ground_truth(
    processed_dir: Path,
    annotation_path: Path,
    output_dir: Path,
) -> None:
    """Check the annotations and write every ground-truth output file."""
    # WARNING: The files below are rebuilt in place. If the annotation CSV
    # changes, this can change ground truth and invalidate prior evaluations.
    # Do not rerun after completing the experiment unless intentionally revising it.
    output_dir.mkdir(parents=True, exist_ok=True)
    reviews = load_reviews(processed_dir)
    annotations = load_annotations(annotation_path)
    check_annotations(annotations, reviews)

    # Use the listing names already attached to the review sample.
    listing_names = (
        reviews.drop_duplicates("listing_id")
        .set_index("listing_id")["listing_name"]
        .to_dict()
    )
    listing_names = {int(key): value for key, value in listing_names.items()}

    # Build the per-review records and the summary tables.
    # Build detailed per-review evidence first; derive all aggregates from the
    # same validated source so the benchmark remains internally consistent.
    records = build_review_records(reviews, annotations)
    aspect_table = flatten_records(records)
    aspect_summary = summarize_aspects(reviews, aspect_table, listing_names)
    issue_summary = summarize_issues(reviews, annotations, listing_names)
    minority_concerns = identify_minority_concerns(issue_summary)

    latest_year = int(reviews["review_year"].max())
    first_recent_year = latest_year - RECENT_WINDOW_YEARS + 1

    # Assemble the listing-level section of the ground truth. Each listing
    # carries its aspect prevalence and the minority concerns that a faithful
    # summary should preserve.
    # Store both aggregate statistics and selected minority concerns for each
    # listing. This is the form consumed by later evaluation stages.
    listings = []
    for listing_id, listing_name in listing_names.items():
        listing_reviews = reviews[reviews["listing_id"] == listing_id]
        representative = listing_reviews[
            listing_reviews["review_set"] == "representative"
        ]
        listing_aspects = aspect_summary[aspect_summary["listing_id"] == listing_id]
        listing_concerns = minority_concerns[
            minority_concerns["listing_id"] == listing_id
        ]

        # Count representative reviews that name no specific aspect (general
        # praise such as "Great place!"). They have no labels but remain part
        # of the listing's total, so recording the count explains why mention
        # shares for a listing can add up to less than expected.
        reviews_without_aspects = sum(
            1
            for record in records
            if record["listing_id"] == listing_id
            and record["review_set"] == "representative"
            and not record["aspects"]
        )

        listings.append(
            {
                "listing_id": listing_id,
                "listing_name": listing_name,
                "representative_reviews": len(representative),
                "challenge_reviews": int(
                    (listing_reviews["review_set"] == "challenge").sum()
                ),
                "first_review_date": representative["date"].min().date().isoformat(),
                "last_review_date": representative["date"].max().date().isoformat(),
                "reviews_without_specific_aspects": reviews_without_aspects,
                "important_aspects": listing_aspects.loc[
                    listing_aspects["important_for_coverage"], "aspect"
                ].tolist(),
                "aspect_prevalence": [
                    {
                        "aspect": row.aspect,
                        "reviews_mentioning": int(row.reviews_mentioning),
                        "mention_share": float(row.mention_share),
                        "prevalence_band": row.prevalence_band,
                        "positive": int(row.positive),
                        "negative": int(row.negative),
                        "mixed": int(row.mixed),
                        "neutral": int(row.neutral),
                        "historical_mention_share": float(row.historical_mention_share),
                        "recent_mention_share": float(row.recent_mention_share),
                    }
                    for row in listing_aspects.itertuples(index=False)
                ],
                "minority_concerns": [
                    {
                        "concern_id": row.concern_id,
                        "issue": row.issue,
                        "aspect": row.aspect,
                        "importance": row.importance,
                        "description": row.description,
                        "selection_reason": row.selection_reason,
                        "evidence_source": row.evidence_source,
                        "representative_reviews_mentioning": int(
                            row.representative_reviews_mentioning
                        ),
                        "challenge_reviews_mentioning": int(
                            row.challenge_reviews_mentioning
                        ),
                        "representative_reviews_praising_aspect": int(
                            row.representative_reviews_praising_aspect
                        ),
                        "first_mention": row.first_mention,
                        "last_mention": row.last_mention,
                        "temporal_status": row.temporal_status,
                        "review_ids": [
                            int(value)
                            for value in (
                                row.representative_review_ids.split("; ")
                                + row.challenge_review_ids.split("; ")
                            )
                            if value
                        ],
                    }
                    for row in listing_concerns.itertuples(index=False)
                ],
            }
        )

    # Metadata documents how the ground truth was produced so the experiment
    # can be described and repeated.
    n_rows = len(annotations)
    # Document provenance and project-specific choices alongside the data.
    # created_on is the rebuild date, not the date the reviews were written.
    metadata = {
        "created_on": date.today().isoformat(),
        "description": (
            "Aspect-level sentiment annotations and derived statistics for "
            "three Airbnb listings, used as the reference point for "
            "evaluating generated property summaries."
        ),
        "annotation_method": (
            "Every review is annotated with the aspects it discusses and "
            "the sentiment toward each, and each evidence quotation is "
            "automatically checked against the original review text."
        ),
        "annotation_rows": n_rows,
        "reviews": {
            "representative": int((reviews["review_set"] == "representative").sum()),
            "challenge": int((reviews["review_set"] == "challenge").sum()),
        },
        "sentiment_labels": SENTIMENT_LABELS,
        "prevalence_bands": {
            label: f"{int(lower * 100)}% to "
            f"{'100%' if upper > 1 else str(int(upper * 100)) + '%'}"
            for lower, upper, label in PREVALENCE_BANDS
        },
        "minority_share_threshold": MINORITY_SHARE_THRESHOLD,
        "periods": {
            "historical": f"before {first_recent_year}",
            "recent": f"{first_recent_year} to {latest_year}",
        },
        "notes": [
            "Prevalence statistics use only the representative sample.",
            "Challenge reviews are annotated so that concerns found only in "
            "them can be tested when they are added to a scenario.",
            "Reviewer names and IDs are not included.",
        ],
    }

    # The JSON retains nested evidence and taxonomy definitions; CSVs below
    # are convenient flat views of selected portions of the same benchmark.
    ground_truth = {
        "metadata": metadata,
        "taxonomy": ASPECT_TAXONOMY,
        "issue_catalog": ISSUE_CATALOG,
        "listings": listings,
        "reviews": records,
    }

    # Write the outputs. The JSON file is the main deliverable; the CSV files
    # hold the same information in a form that is easier to inspect.
    with open(output_dir / "ground_truth.json", "w", encoding="utf-8") as file:
        json.dump(ground_truth, file, indent=2, ensure_ascii=False)

    with open(output_dir / "aspect_taxonomy.json", "w", encoding="utf-8") as file:
        json.dump(
            {"aspects": ASPECT_TAXONOMY, "issues": ISSUE_CATALOG},
            file,
            indent=2,
            ensure_ascii=False,
        )

    aspect_table.to_csv(output_dir / "review_aspects.csv", index=False)
    aspect_summary.to_csv(output_dir / "aspect_prevalence.csv", index=False)
    issue_summary.to_csv(output_dir / "issue_timeline.csv", index=False)
    minority_concerns.to_csv(output_dir / "minority_concerns.csv", index=False)

    # Print a compact summary of what was produced.
    print("\nGround-truth preparation is complete.")
    print(f"Files saved to: {output_dir.resolve()}")
    print(
        f"\nAnnotations checked: {n_rows} rows across "
        f"{annotations['review_id'].nunique()} of {len(reviews)} reviews; "
        "every evidence quotation was found in its review."
    )

    print("\nRepresentative reviews that name no specific aspect:")
    for listing in listings:
        print(
            f"  {listing['listing_name']}: "
            f"{listing['reviews_without_specific_aspects']}"
        )

    print("\nMost discussed aspects (share of representative reviews):")
    top_aspects = (
        aspect_summary.sort_values(
            ["listing_id", "mention_share"], ascending=[True, False]
        )
        .groupby("listing_id")
        .head(4)
    )
    print(
        top_aspects[
            ["listing_name", "aspect", "mention_share", "prevalence_band"]
        ].to_string(index=False)
    )

    print("\nImportant minority concerns:")
    print(
        minority_concerns[
            [
                "listing_name",
                "issue",
                "importance",
                "representative_reviews_mentioning",
                "challenge_reviews_mentioning",
                "temporal_status",
            ]
        ].to_string(index=False)
    )


def main() -> None:
    # Optional command-line paths make it possible to rebuild the benchmark
    # from a different sample or annotation file without editing the script.
    parser = argparse.ArgumentParser(
        description="Build the ground-truth benchmark for the review sample."
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Folder containing selected_reviews.csv and challenge_reviews.csv "
        "(default: data/processed).",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=DEFAULT_ANNOTATION_PATH,
        help="Annotation CSV (default: data/annotations/annotations.csv).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for generated benchmark files (default: data/benchmark).",
    )
    args = parser.parse_args()

    build_ground_truth(
        processed_dir=args.processed_dir,
        annotation_path=args.annotations,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
