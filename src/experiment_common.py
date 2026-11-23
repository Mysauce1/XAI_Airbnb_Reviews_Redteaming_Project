"""
Shared helper functions for the Airbnb review-summarization experiment.

This module contains utilities used across the experiment to:
- Read and write CSV and JSON files.
- Generate file hashes for reproducibility checks.
- Load and validate baseline and adversarial review scenarios.
- Prepare reviews in a consistent format for the summarization models.
- Load prompt templates and process structured model responses.

Keeping these functions in one module ensures that the different
experimental systems use the same data-loading, formatting, and
validation procedures.

The functions do not make API requests or run experiments themselves.
"""

from __future__ import annotations

# Read and write CSV files using Python's standard library.
import csv

# Generate SHA-256 hashes to identify specific file contents.
import hashlib

# Read, write, and serialize JSON data.
import json

# Imported in the original script but not currently used.
import os

# Handle regular expressions, used to remove Markdown formatting
# from JSON responses returned by language models.
import re

# Construct file paths in a way that works across operating systems.
from pathlib import Path

# Locate the project root based on this script's location.
#
# __file__ refers to the path of experiment_common.py.
# resolve() converts it to an absolute path.
# parent.parent moves from src/ to the project root.
#
# Using this approach avoids depending on the directory from which
# the user runs the experiment.
ROOT = Path(__file__).resolve().parent.parent


# The cutoff date for reviews included in the experiment.
#
# Reviews dated after September 30, 2026 are rejected when preparing
# the model inputs. This keeps the experiment aligned with the
# available review data and prevents future-dated information
# from entering the summarization process.
AS_OF = "2026-09-30"


# Calendar years treated as recent in the experimental setup.
#
# These years can be supplied to the summarization prompts to help
# distinguish recent experiences from historical concerns.
#
# This constant defines the years but does not independently
# classify reviews as recent or historical.
RECENT_YEARS = (2024, 2025, 2026)


def read_csv(path):
    """
    Read a CSV file and return its contents as a list of dictionaries.

    Each dictionary represents one row, with column names as keys.

    CSV values are returned as strings. This is important because
    identifiers should generally be preserved exactly as written.
    """

    # utf-8-sig handles ordinary UTF-8 files and files that begin
    # with a UTF-8 byte order mark (BOM), which some spreadsheet
    # applications include when exporting CSV files.
    #
    # newline="" allows the csv module to handle line endings
    # correctly across different operating systems.
    with Path(path).open(encoding="utf-8-sig", newline="") as f:

        # DictReader uses the first row as column names.
        # Converting the reader to a list loads all rows into memory.
        return list(csv.DictReader(f))


def read_json(path):
    """
    Read a JSON file and convert it into Python data structures.

    JSON objects become dictionaries, arrays become lists, and
    JSON values become their corresponding Python types.
    """

    # Read the file as UTF-8 text, then parse its JSON contents.
    # Invalid JSON raises an error rather than being silently ignored.
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    """
    Save Python data as a formatted JSON file.

    Creates the destination directory if it does not exist.
    Existing files at the destination are overwritten.
    """

    # Convert the supplied path into a Path object.
    path = Path(path)

    # Create any missing parent directories.
    #
    # parents=True allows multiple directory levels to be created.
    # exist_ok=True prevents an error if they already exist.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize the data and write it to disk.
    #
    # indent=2 makes the output easier to inspect manually.
    # ensure_ascii=False preserves non-ASCII characters, such as
    # accented letters and typographic punctuation.
    #
    # The output is useful for saving model responses, evaluation
    # records, and intermediate evidence used during auditing.
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path, rows, columns):
    """
    Write a collection of dictionaries to a CSV file.

    Parameters
    ----------
    path : str or Path
        Destination file.

    rows : iterable of dict
        Records to write.

    columns : list of str
        Column names and their order in the output file.

    Any dictionary keys not included in columns are ignored.
    """

    path = Path(path)

    # Make sure the destination folder exists before writing.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Open the file in write mode.
    #
    # newline="" prevents extra blank lines when writing CSV files,
    # particularly on Windows.
    with path.open("w", newline="", encoding="utf-8") as f:

        # DictWriter maps dictionary values to the specified columns.
        #
        # extrasaction="ignore" means additional dictionary fields
        # are excluded instead of causing an error.
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")

        # Write the column names, followed by the data rows.
        #
        # If a row is missing one of the requested columns,
        # DictWriter writes an empty field for that column.
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    """
    Calculate the SHA-256 hash of a file.

    The hash acts as a fingerprint of the file's contents.
    It can be saved alongside experimental results to help
    verify that the same input files or prompts were used.

    Even a small change to a file will generally produce a
    different hash.
    """

    # Read the raw file bytes rather than decoded text.
    # This makes the hash sensitive to the exact stored contents,
    # including whitespace and line-ending differences.
    #
    # hexdigest() returns the hash as a hexadecimal string.
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_scenarios():
    """
    Load and validate the baseline and adversarial review scenarios.

    Returns
    -------
    manifest : list of dict
        Scenario metadata describing the experimental conditions.

    groups : dict
        Dictionary mapping each scenario ID to its review records.

    Validation checks include:
    - Required columns exist in the input files.
    - Scenario IDs are unique in the manifest.
    - Every review belongs to a recognized scenario.
    - No scenario is empty.
    - Review IDs are unique within each scenario.

    These checks help prevent data-organization errors from
    affecting the comparison between experimental conditions.
    """

    # Locate the directory containing the scenario definitions
    # generated during the adversarial review construction step.
    folder = ROOT / "data/adversarial"

    # Load the scenario manifest and review-level scenario inputs.
    #
    # The manifest contains one row per experimental scenario.
    # The inputs contain the reviews assigned to each scenario.
    manifest = read_csv(folder / "scenario_manifest.csv")
    inputs = read_csv(folder / "scenario_inputs.csv")

    # Columns required to identify each experimental condition.
    #
    # These fields distinguish baselines from attacks and allow
    # results to be grouped by listing, attack type, variant,
    # and injection intensity.
    expected = {
        "scenario_id",
        "listing_id",
        "scenario_type",
        "attack_type",
        "attack_variant",
        "intensity",
    }

    # Confirm that the manifest contains at least one row and
    # includes the expected columns.
    #
    # manifest[0] represents the first row as a dictionary.
    # Checking its keys establishes whether the expected
    # column names were read from the CSV.
    #
    # assert raises an AssertionError if the condition fails.
    assert manifest and expected.issubset(manifest[0]), "Missing manifest columns"

    # Define the minimum fields needed for each scenario review.
    #
    # The review ID supports evidence traceability.
    # The date supports temporal reasoning.
    # The text is what the summarization models analyze.
    required = {
        "scenario_id",
        "review_id",
        "review_date",
        "text",
    }

    # Confirm that scenario_inputs.csv is nonempty and includes
    # all required fields.
    assert inputs and required.issubset(inputs[0]), "Missing scenario input columns"

    # Collect every scenario ID defined in the manifest.
    ids = [r["scenario_id"] for r in manifest]

    # A set contains only unique values.
    #
    # If the set is smaller than the original list, at least
    # one scenario ID appears more than once.
    #
    # Duplicate scenario IDs could cause reviews from different
    # conditions to be combined incorrectly.
    assert len(ids) == len(set(ids)), "Duplicate scenario IDs"

    # Create an empty list for each scenario.
    #
    # This structure will be populated with the reviews assigned
    # to that scenario.
    groups = {i: [] for i in ids}

    # Assign every review row to its corresponding scenario.
    for row in inputs:

        # Reject review records that refer to an undefined scenario.
        #
        # This helps ensure the model is only run on scenarios
        # explicitly documented in the experiment manifest.
        if row["scenario_id"] not in groups:
            raise ValueError("Unknown scenario ID")

        groups[row["scenario_id"]].append(row)

    # Validate the review collection for every scenario.
    for key, group in groups.items():

        # Each scenario must contain at least one review.
        # An empty scenario would not provide meaningful input
        # for summarization.
        if not group:
            raise ValueError(f"Empty scenario: {key}")

        # Confirm that review IDs are unique within the scenario.
        #
        # The same genuine review may appear across multiple
        # scenarios because the experiment uses shared baselines.
        # That is expected and is not rejected here.
        #
        # However, the same review ID appearing twice within
        # one scenario would risk double-counting that review.
        if len({str(r["review_id"]) for r in group}) != len(group):
            raise ValueError(f"Duplicate review ID within {key}")

    # Return both the experimental metadata and the review
    # collections for use by the summarization pipeline.
    return manifest, groups


def visible_reviews(rows):
    """
    Prepare a scenario's reviews for submission to a model.

    The function:
    - Sorts reviews by date and original review ID.
    - Rejects reviews dated after the experiment cutoff.
    - Replaces original review IDs with neutral sequential IDs.
    - Retains the review date and text.

    This gives the models a consistent input format without
    exposing the original review identifiers.

    It does not remove synthetic review text, rewrite dates,
    or distinguish genuine reviews from injected reviews.
    """

    # Store the reviews in the format expected by the models.
    clean = []

    # Sort chronologically, using review ID to break ties.
    #
    # This makes the order deterministic for a given input.
    # The same collection of reviews will produce the same
    # ordering regardless of their original CSV row order.
    #
    # The dates are compared as strings, which works for
    # consistently formatted ISO dates (YYYY-MM-DD).
    ordered = sorted(rows, key=lambda r: (r["review_date"], str(r["review_id"])))

    # Assign new sequential IDs after sorting.
    #
    # Starting at 1 produces identifiers such as R0001, R0002,
    # and R0003.
    #
    # Both genuine and synthetic reviews receive the same ID
    # format, so the identifier itself does not reveal whether
    # a review was injected.
    for index, row in enumerate(ordered, start=1):

        # Exclude reviews that fall after the cutoff date.
        #
        # This protects the temporal consistency of the experiment.
        #
        # Like the sorting operation, this comparison assumes
        # review dates use the YYYY-MM-DD format.
        if row["review_date"] > AS_OF:
            raise ValueError("Review after cutoff date")

        # Keep only the fields needed by the summarization model.
        #
        # The original review ID and any experimental metadata
        # are not included in this model-facing record.
        #
        # Importantly, the review text is left unchanged.
        clean.append(
            {
                "review_id": f"R{index:04d}",
                "date": row["review_date"],
                "text": row["text"],
            }
        )

    # Return the consistently formatted model input.
    return clean


def prompt(name):
    """
    Load a prompt template from the project's prompts directory.

    Keeping prompts in separate text files makes them easier
    to inspect, revise, and version independently of the code.
    """

    # Construct the prompt path and return its contents.
    # A missing file raises FileNotFoundError.
    return (ROOT / "prompts" / name).read_text(encoding="utf-8")


def parse_json_reply(text):
    """
    Parse a JSON response returned by a language model.

    Some models wrap JSON responses in Markdown code fences,
    even when JSON was requested.

    This function removes an outer Markdown code fence when
    present, then parses the remaining text as JSON.

    It does not attempt to repair malformed JSON.
    """

    # Remove leading and trailing whitespace.
    text = text.strip()

    # Check whether the response begins with a Markdown code fence.
    if text.startswith("```"):

        # Remove an opening ``` or ```json marker and a closing
        # ``` marker, along with surrounding whitespace.
        #
        # The regular expression is intended for common fenced
        # JSON responses, not arbitrary Markdown documents.
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()

    # Convert the cleaned response into Python data.
    #
    # If the text is not valid JSON, json.loads() raises
    # JSONDecodeError so the problem can be handled upstream.
    return json.loads(text)


def canonical(value):
    """
    Serialize Python data into a consistent JSON string.

    Sorting dictionary keys makes the serialized representation
    more predictable across calls, which is useful when logging
    model inputs or comparing experimental requests.

    Non-ASCII characters are preserved rather than escaped.
    """

    # sort_keys=True ensures consistent dictionary-key ordering.
    #
    # This does not sort lists, so the order of reviews and
    # evidence items remains unchanged.
    #
    # The result is a JSON string, not a Python dictionary.
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
