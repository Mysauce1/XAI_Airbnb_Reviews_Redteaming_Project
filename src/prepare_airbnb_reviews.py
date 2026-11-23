"""
Prepare the Airbnb review sample.

Run this script from the project root or src folder after placing the original CSV files in
``data/raw/``. It creates the sampled reviews and supporting files in
``data/processed/``.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

# Locate the project root (the parent folder of src).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The raw CSVs stay unchanged. All files created by this script go in
# data/processed so that the original data and our working data remain separate.
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

# A fixed seed makes the random selections repeatable when the source CSVs,
# filtering rules, and pandas sampling behavior are unchanged. Each year uses
# this seed plus its calendar year, so sampling within a year is reproducible.
RANDOM_SEED = 42
# Aim for 100 representative reviews per listing. If fewer eligible reviews
# exist, the sampler keeps all eligible reviews instead of sampling with replacement.
TARGET_REVIEWS_PER_LISTING = 100
# Exclude very short comments from the representative sample because they
# usually provide little aspect-specific evidence. This is a character count,
# not a word count; challenge reviews are handled separately.
MIN_COMMENT_CHARACTERS = 30

# Only these three properties are included. The IDs must match the IDs in
# reviews.csv and listings.csv; names are stable labels for project outputs.
LISTINGS = {
    3314819: "Basement: Mountainside Private Room & Private Bath",
    660702: "Cozy Asheville Retreat",
    7947839: "Romantic & Bohemian Private Studio",
}

# These are the row numbers in the original reviews.csv, counting the header
# as row 1. We save these reviews separately as a challenge set rather than
# mixing them into the representative sample.
CHALLENGE_SOURCE_ROWS = {
    3314819: [17838, 18055, 18075, 18094],
    660702: [1921, 1933, 2060, 2120],
    7947839: [38302],
}

# Read only fields needed to identify, date, and analyze review text.
# Keeping fewer columns reduces memory use for a large raw reviews file.
REVIEW_COLUMNS = ["listing_id", "id", "date", "comments"]

# Keep only listing information that may be useful when describing the
# properties or interpreting the review results. Host contact information
# and other unnecessary identifying fields are not included.
LISTING_COLUMNS = [
    "id",
    "name",
    "property_type",
    "room_type",
    "accommodates",
    "bedrooms",
    "beds",
    "bathrooms_text",
    "description",
    "neighborhood_overview",
    "first_review",
    "last_review",
    "number_of_reviews",
    "review_scores_rating",
    "review_scores_accuracy",
    "review_scores_cleanliness",
    "review_scores_checkin",
    "review_scores_communication",
    "review_scores_location",
    "review_scores_value",
]


def load_source_data(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the two source files needed for this step from data/raw."""
    reviews_path = raw_dir / "reviews.csv"
    listings_path = raw_dir / "listings.csv"

    # Fail early with a useful message if the files have not been moved into
    # the expected folder or if their filenames differ.
    missing_files = [
        path.name for path in (reviews_path, listings_path) if not path.exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            f"Missing {', '.join(missing_files)} in {raw_dir.resolve()}. "
            "Place reviews.csv and listings.csv in data/raw/ and try again."
        )

    # usecols avoids loading unused columns. low_memory=False lets pandas
    # infer column types from the file as a whole rather than chunk-by-chunk.
    reviews = pd.read_csv(
        reviews_path,
        usecols=REVIEW_COLUMNS,
        low_memory=False,
    )
    # Listing metadata varies between Airbnb exports. The callable keeps
    # whichever requested metadata columns are actually available, avoiding
    # an error when an optional listing column is missing.
    listings = pd.read_csv(
        listings_path,
        usecols=lambda column: column in LISTING_COLUMNS,
        low_memory=False,
    )

    # Keep the original CSV row number. Since pandas starts its index at 0 and
    # the CSV header occupies row 1, adding 2 gives the Excel row number.
    reviews = reviews.reset_index(drop=True)
    reviews.insert(0, "source_row_number", reviews.index + 2)

    # Standardize the fields used for filtering and sampling. Invalid dates
    # become NaT and are excluded from the representative sample below.
    # Use pandas' nullable Int64 type so invalid or missing listing IDs can
    # remain missing during filtering instead of causing a conversion error.
    reviews["listing_id"] = pd.to_numeric(
        reviews["listing_id"], errors="coerce"
    ).astype("Int64")
    # Invalid date strings become NaT (pandas' missing datetime value).
    # The representative sample later excludes rows with missing dates.
    reviews["date"] = pd.to_datetime(reviews["date"], errors="coerce")
    # Treat missing comments as empty strings and strip surrounding spaces.
    # This makes the minimum-length filter consistent across rows.
    reviews["comments"] = reviews["comments"].fillna("").astype(str).str.strip()
    listings["id"] = pd.to_numeric(listings["id"], errors="coerce").astype("Int64")

    return reviews, listings


def allocate_yearly_sample(year_counts: pd.Series, target_n: int) -> dict[int, int]:
    """Split the requested sample across years in proportion to review counts."""
    # Keep calendar years in a stable order before computing allocations.
    # The allocation uses the number of eligible reviews in each year, not
    # an equal number of reviews from every year.
    counts = year_counts.sort_index()
    total = int(counts.sum())
    if total == 0:
        return {}

    # If there are fewer eligible reviews than requested, use all of them.
    target_n = min(target_n, total)

    # First assign the whole-number portion of each year's proportional share.
    # These are fractional quotas. For example, a year representing 20% of
    # eligible reviews receives an initial quota of 20 out of a 100-review
    # sample. Flooring the quotas avoids overallocating any year.
    exact_shares = counts / total * target_n
    allocation = exact_shares.apply(math.floor).astype(int)

    # Assign any remaining places to the years with the largest fractional
    # remainders. This makes the allocations add up to the requested total.
    places_left = target_n - int(allocation.sum())
    # Use the largest-remainder method to distribute slots lost to flooring.
    # This keeps the final sample size equal to target_n while closely
    # approximating the original distribution of reviews across years.
    # Tied remainders follow pandas' sort behavior.
    fractional_remainders = (exact_shares - allocation).sort_values(ascending=False)
    for year in fractional_remainders.index:
        if places_left == 0:
            break
        # Never request more reviews from a year than actually exist.
        if allocation.loc[year] < counts.loc[year]:
            allocation.loc[year] += 1
            places_left -= 1

    return {int(year): int(n) for year, n in allocation.items() if n > 0}


def make_year_stratified_sample(
    listing_reviews: pd.DataFrame,
    target_n: int,
    seed: int,
) -> pd.DataFrame:
    """Take a reproducible sample while retaining the distribution across years."""
    # Work on a copy so the temporary review_year column does not alter
    # the original eligible-review table used elsewhere in the script.
    data = listing_reviews.copy()
    data["review_year"] = data["date"].dt.year
    data = data.dropna(subset=["review_year"])
    data["review_year"] = data["review_year"].astype(int)

    # Calculate how many reviews to draw from each year, then sample within
    # each year. Using a year-specific seed keeps the result reproducible.
    reviews_per_year = data.groupby("review_year").size()
    allocation = allocate_yearly_sample(reviews_per_year, target_n)

    # Draw the allocated number of rows independently within each year.
    # pandas.sample() samples without replacement by default, so a review
    # cannot be selected twice from the same year.
    sampled_years = []
    for year, sample_size in allocation.items():
        reviews_from_year = data[data["review_year"] == year]
        sampled_years.append(
            reviews_from_year.sample(
                n=sample_size,
                # A fixed, year-specific seed prevents a different number
                # of reviews in one year from changing another year's draw.
                random_state=seed + year,
            )
        )

    # If no year has eligible reviews, return an empty DataFrame with the
    # expected columns rather than failing while concatenating an empty list.
    if not sampled_years:
        return data.iloc[0:0].copy()

    # Sort the finished sample chronologically to make it easier to inspect.
    return (
        pd.concat(sampled_years, ignore_index=True)
        .sort_values(["date", "id"])
        .reset_index(drop=True)
    )


def prepare_datasets(
    raw_dir: Path,
    output_dir: Path,
    target_n: int = TARGET_REVIEWS_PER_LISTING,
    min_chars: int = MIN_COMMENT_CHARACTERS,
    seed: int = RANDOM_SEED,
) -> None:
    """Create the representative sample, challenge set, and summary files."""
    # Create the processed-data directory before writing output files.
    # The raw source files are only read; they are never overwritten.
    output_dir.mkdir(parents=True, exist_ok=True)
    reviews, listings = load_source_data(raw_dir)

    # Start with reviews belonging to the three properties selected for the
    # project. Other listings in the full Airbnb dataset are not needed here.
    selected_ids = list(LISTINGS)
    project_reviews = reviews[reviews["listing_id"].isin(selected_ids)].copy()
    # Store lengths so the eligibility decision can be inspected later.
    project_reviews["comment_length"] = project_reviews["comments"].str.len()

    # For the representative sample, require a nontrivial comment and a valid
    # date so each review can be assigned to a year.
    usable_reviews = project_reviews[
        (project_reviews["comment_length"] >= min_chars)
        & project_reviews["date"].notna()
    ].copy()

    # Retrieve the preselected critical examples using their original CSV row
    # numbers. Check that every row exists and belongs to the expected listing;
    # this catches accidental changes to the source file or row numbering.
    # Flatten the listing-specific challenge row numbers into one list.
    # These are 1-based source CSV row numbers, including the header,
    # rather than pandas' 0-based DataFrame positions.
    challenge_rows = [row for rows in CHALLENGE_SOURCE_ROWS.values() for row in rows]
    challenge_reviews = project_reviews[
        project_reviews["source_row_number"].isin(challenge_rows)
    ].copy()

    # Confirm every specified challenge row was found among the selected
    # listings. This count check also catches missing or misidentified rows.
    if len(challenge_reviews) != len(challenge_rows):
        found_rows = set(challenge_reviews["source_row_number"].astype(int))
        missing_rows = sorted(set(challenge_rows) - found_rows)
        raise ValueError(f"Challenge review rows not found: {missing_rows}")

    # Verify that the retrieved rows belong to their expected property.
    # A changed source CSV ordering could otherwise silently substitute
    # a different review for a hand-selected challenge example.
    for listing_id, group in challenge_reviews.groupby("listing_id"):
        expected_rows = set(CHALLENGE_SOURCE_ROWS[int(listing_id)])
        actual_rows = set(group["source_row_number"].astype(int))
        if actual_rows != expected_rows:
            raise ValueError(
                f"Unexpected challenge rows for listing {listing_id}. "
                f"Expected {expected_rows}, found {actual_rows}."
            )

    # Hold challenge examples out of the representative sample. They were
    # selected because they describe notable problems, so including them in a
    # random sample would distort estimates of how common those problems are.
    eligible_reviews = usable_reviews[
        ~usable_reviews["source_row_number"].isin(challenge_rows)
    ].copy()

    # Accumulate each listing's representative sample and a separate
    # sampling audit row. No challenge review is eligible for these draws.
    samples = []
    summary_rows = []

    for listing_id, listing_name in LISTINGS.items():
        listing_reviews = eligible_reviews[
            eligible_reviews["listing_id"] == listing_id
        ].copy()

        # Apply the same target size, minimum-length rule, and random seed
        # to all three listings. Stratification preserves the approximate
        # distribution of eligible reviews across calendar years.
        sample = make_year_stratified_sample(
            listing_reviews,
            target_n=target_n,
            seed=seed,
        )
        # Add a human-readable property label to each sampled review.
        sample.insert(0, "listing_name", listing_name)
        samples.append(sample)

        # Record the number of selected reviews from each year so the sampling
        # process can be described and checked later.
        year_counts = sample.groupby(sample["date"].dt.year).size().to_dict()
        summary_rows.append(
            {
                "listing_id": listing_id,
                "listing_name": listing_name,
                "eligible_reviews_before_sampling": len(listing_reviews),
                "target_sample_size": target_n,
                "actual_sample_size": len(sample),
                "first_sampled_review_date": (
                    sample["date"].min().date().isoformat()
                    if not sample.empty
                    else None
                ),
                "last_sampled_review_date": (
                    sample["date"].max().date().isoformat()
                    if not sample.empty
                    else None
                ),
                "sampled_reviews_by_year": "; ".join(
                    f"{year}: {count}" for year, count in sorted(year_counts.items())
                ),
            }
        )

    # Combine the three independent listing samples into one file.
    # ignore_index=True assigns a fresh continuous DataFrame index.
    selected_reviews = pd.concat(samples, ignore_index=True)

    # Keep the challenge set separate. These reviews are useful for testing
    # whether the summarizer preserves important concerns, but they are not
    # part of the representative sample.
    # Challenge reviews need nonempty text, but they are intentionally NOT
    # subjected to the representative sample's 30-character cutoff.
    challenge_reviews = challenge_reviews[
        challenge_reviews["comments"].str.len() > 0
    ].copy()
    challenge_reviews["listing_name"] = challenge_reviews["listing_id"].map(LISTINGS)
    challenge_reviews["review_year"] = challenge_reviews["date"].dt.year

    # Reviewer names and IDs are not needed for the project, so neither is
    # written to the output files. The source row and review ID remain for
    # traceability within the research workflow.
    output_columns = [
        "listing_name",
        "listing_id",
        "id",
        "date",
        "review_year",
        "comments",
        "comment_length",
        "source_row_number",
    ]

    # Recalculate comment lengths and export dates as ISO strings so the
    # resulting CSVs can be used consistently by downstream scripts.
    for frame in (selected_reviews, challenge_reviews):
        frame["comment_length"] = frame["comments"].str.len()
        frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")

    # Write representative and challenge data to separate CSV files.
    # Both files retain source review IDs and original row numbers for
    # traceability, but omit reviewer names and reviewer account IDs.
    selected_reviews[output_columns].to_csv(
        output_dir / "selected_reviews.csv", index=False
    )
    challenge_reviews[output_columns].to_csv(
        output_dir / "challenge_reviews.csv", index=False
    )

    # Save the selected listings with only the metadata columns that are
    # available in the source file and relevant to this project.
    available_listing_columns = [
        column for column in LISTING_COLUMNS if column in listings.columns
    ]
    # Retain only the selected listings and the metadata actually present
    # in the source export; add the project's stable display names.
    selected_listings = listings[listings["id"].isin(selected_ids)][
        available_listing_columns
    ].copy()
    selected_listings["project_listing_name"] = selected_listings["id"].map(LISTINGS)
    selected_listings.to_csv(output_dir / "selected_listings.csv", index=False)

    # Save a compact record of the sample sizes and year distributions.
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(output_dir / "sampling_summary.csv", index=False)

    # This file makes it easy to verify that the challenge reviews were kept
    # separate from the representative sample for each property.
    # Produce a quick check of how many representative and challenge
    # reviews were retained for each listing. These are counts, not
    # estimates of how prevalent a particular issue is.
    audit = pd.DataFrame(
        [
            {
                "listing_id": listing_id,
                "listing_name": LISTINGS[listing_id],
                "challenge_reviews_held_out": int(
                    (challenge_reviews["listing_id"] == listing_id).sum()
                ),
                "representative_reviews_selected": int(
                    (selected_reviews["listing_id"] == listing_id).sum()
                ),
            }
            for listing_id in LISTINGS
        ]
    )
    audit.to_csv(output_dir / "selection_audit.csv", index=False)

    print("\nAirbnb review preparation is complete.")
    print(f"Files saved to: {output_dir.resolve()}")
    print("\nRepresentative sample:")
    print(summary.to_string(index=False))
    print("\nChallenge set:")
    print(audit.to_string(index=False))
    print(
        "\nKeep challenge_reviews.csv separate from selected_reviews.csv "
        "when calculating issue prevalence."
    )


def main() -> None:
    # Command-line options allow alternative data folders and sampling
    # parameters without editing the script. Defaults match the project
    # structure used in the rest of the experiment.
    parser = argparse.ArgumentParser(description="Prepare the Airbnb review sample.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help="Folder containing reviews.csv and listings.csv (default: data/raw).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for generated CSV files (default: data/processed).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=TARGET_REVIEWS_PER_LISTING,
        help="Target number of representative reviews per listing.",
    )
    parser.add_argument(
        "--min-comment-chars",
        type=int,
        default=MIN_COMMENT_CHARACTERS,
        help="Minimum comment length for the representative sample.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=RANDOM_SEED,
        help="Random seed used for reproducible sampling.",
    )
    args = parser.parse_args()

    # A zero or negative sample size / character threshold would make the
    # sampling request nonsensical, so reject these inputs early.
    if args.sample_size < 1:
        parser.error("--sample-size must be at least 1")
    if args.min_comment_chars < 1:
        parser.error("--min-comment-chars must be at least 1")

    # Run the pipeline only after all command-line arguments are parsed
    # and validated. This is the only entry point that writes outputs.
    prepare_datasets(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        target_n=args.sample_size,
        min_chars=args.min_comment_chars,
        seed=args.seed,
    )


# Importing this file defines its functions and constants without
# preparing data. Running it directly executes the CLI entry point.
if __name__ == "__main__":
    main()
