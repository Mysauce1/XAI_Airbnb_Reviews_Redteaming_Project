"""
Run fast unit tests for the Airbnb red-teaming experiment.

These tests check several important assumptions about the shared
experiment utilities before the full summarization pipeline is run.

The tests focus on four areas:

1. Provenance separation:
   Verify that synthetic-review labels and attack metadata are
   excluded from the review dictionaries supplied to the models.

2. Temporal validity:
   Verify that reviews dated after the experiment's cutoff
   (September 30, 2026) are rejected.

3. JSON response parsing:
   Verify that the JSON parser can handle responses enclosed
   in Markdown code fences.

4. File hashing:
   Verify that hashing an unchanged file produces the same
   SHA-256 digest across repeated calls.

These are unit tests, not full end-to-end experiment tests.

They do not:
- Make API requests.
- Generate summaries.
- Evaluate attack success.
- Verify the accuracy of model-generated claims.
- Modify the project's experimental datasets.

The tests use Python's built-in unittest framework and can
be run locally without consuming model API tokens.
"""

# Provides access to Python's module search path.
#
# This is used to make the project's src/ directory
# available for importing experiment_common.py.
import sys

# Provides temporary files and directories for testing.
#
# TemporaryDirectory() creates an isolated directory that
# is automatically removed when the test finishes.
import tempfile

# Python's built-in unit testing framework.
#
# unittest provides:
# - TestCase classes.
# - Assertions for checking expected behavior.
# - Utilities for verifying expected exceptions.
# - A test runner that reports passes, failures, and errors.
import unittest

# Provides an object-oriented interface for working
# with filesystem paths.
from pathlib import Path

# Locate the project root directory.
#
# __file__ refers to the current test script.
# resolve() converts the file path to an absolute path.
# parents[1] moves up two directory levels:
#
# For example:
# project/
#     src/
#         experiment_common.py
#     tests/
#         test_experiment_contracts.py
#
# From tests/test_experiment_contracts.py,
# parents[1] points to project/.
#
# This assumes the test file is stored one directory
# below the project root.
ROOT = Path(__file__).resolve().parents[1]


# Add the project's src/ directory to Python's import path.
#
# Python searches directories in sys.path when resolving imports.
#
# Inserting src/ at position 0 makes Python search that
# directory first.
#
# This allows the test script to import experiment_common
# without requiring the project to be installed as a package.
sys.path.insert(0, str(ROOT / "src"))


# Import the specific helper functions being tested.
#
# visible_reviews():
#   Converts raw scenario reviews into the standardized
#   representation used as model input.
#
# parse_json_reply():
#   Parses JSON text, including responses enclosed in
#   Markdown code fences.
#
# digest():
#   Calculates the SHA-256 hash of a file's contents.
#
# Importing these helpers does not send model API requests.
from experiment_common import (
    visible_reviews,
    parse_json_reply,
    digest,
)


# Define a collection of related unit tests.
#
# Inheriting from unittest.TestCase provides assertion methods
# and allows unittest to discover and execute the tests.
#
# By convention, test methods begin with "test_".
# unittest automatically recognizes these methods as tests.
class ExperimentContractTests(unittest.TestCase):

    def test_provenance_never_reaches_model(self):
        """
        Verify that provenance and attack metadata are excluded
        from the standardized model-visible review dictionaries.

        The experiment uses metadata such as is_synthetic,
        attack_variant, and target_issue to track manipulations.

        However, the summarization systems and blind claim judge
        should not receive these labels as part of their
        model-visible review records.

        This test checks that visible_reviews() returns only
        the expected review ID, date, and text fields.

        It does not verify every API call or every possible
        source of metadata leakage elsewhere in the pipeline.
        """

        # Create a small example of a raw scenario review.
        #
        # The review includes the normal fields needed by
        # the summarization systems:
        # - review_id
        # - review_date
        # - text
        #
        # It also contains experimental metadata:
        # - is_synthetic identifies a fabricated review.
        # - attack_variant identifies the manipulation type.
        # - target_issue identifies the concern being targeted.
        #
        # These additional fields should remain available
        # for experiment management but should not appear
        # in the model-visible review dictionary.
        raw = [
            {
                "review_id": "123",
                "review_date": "2026-09-01",
                "text": "Quiet stay",
                "is_synthetic": "True",
                "attack_variant": "aspect_specific_counterevidence",
                "target_issue": "noise",
            }
        ]

        # Convert the raw review to the standardized format.
        #
        # visible_reviews() assigns neutral sequential IDs,
        # renames review_date to date, and retains the text.
        #
        # It does not copy the extra provenance fields.
        clean = visible_reviews(raw)

        # Verify that the complete output matches the
        # expected model-visible representation.
        #
        # assertEqual() compares the two Python objects
        # and fails the test if they differ.
        #
        # The expected output contains exactly three fields:
        # review_id, date, and text.
        #
        # The original review ID is replaced with R0001.
        self.assertEqual(
            clean,
            [
                {
                    "review_id": "R0001",
                    "date": "2026-09-01",
                    "text": "Quiet stay",
                }
            ],
        )

        # Explicitly verify that the synthetic-review label
        # is not present in the cleaned review.
        #
        # assertNotIn() fails if the specified key exists.
        #
        # This check reinforces the provenance-separation
        # requirement, although the exact-dictionary assertion
        # above already excludes all additional fields.
        self.assertNotIn("is_synthetic", clean[0])

    def test_future_review_is_rejected(self):
        """
        Verify that reviews dated after the experimental
        cutoff are rejected.

        The experiment uses September 30, 2026 as its
        cutoff date.

        A review dated October 1, 2026 should therefore
        trigger a ValueError.

        This helps prevent future-dated evidence from
        entering the summarization experiment.
        """

        # assertRaises() verifies that the enclosed operation
        # raises the specified exception.
        #
        # If visible_reviews() raises ValueError, the test passes.
        #
        # If it returns normally or raises an unexpected
        # exception type, the test fails or reports an error.
        with self.assertRaises(ValueError):

            # Supply a review dated one day after the cutoff.
            #
            # visible_reviews() compares the review date
            # against the AS_OF constant in experiment_common.py.
            #
            # The review should be rejected before a
            # model-visible collection is returned.
            visible_reviews(
                [
                    {
                        "review_id": "1",
                        "review_date": "2026-10-01",
                        "text": "test",
                    }
                ]
            )

    def test_json_code_fence(self):
        """
        Verify that JSON enclosed in a Markdown code fence
        can be parsed correctly.

        Language models sometimes wrap JSON responses in
        Markdown formatting, even when instructed to
        return JSON only.

        parse_json_reply() is designed to remove common
        code-fence formatting before parsing the JSON.

        This test checks one typical fenced-JSON response.
        """

        # Simulate a model response containing a JSON object
        # enclosed in a Markdown code fence.
        #
        # The string contains:
        # - An opening ```json fence.
        # - A JSON object with a summary field.
        # - A closing ``` fence.
        #
        # \n represents newline characters.
        fenced_response = "```json\n" '{"summary":"ok"}\n' "```"

        # Verify that parse_json_reply() removes the fences
        # and converts the JSON into a Python dictionary.
        #
        # The expected dictionary contains:
        # {"summary": "ok"}
        #
        # This test verifies successful parsing, but it
        # does not validate a complete summary schema.
        self.assertEqual(parse_json_reply(fenced_response), {"summary": "ok"})

    def test_sha256_is_deterministic(self):
        """
        Verify that an unchanged file produces the same
        SHA-256 digest when hashed repeatedly.

        The experiment uses file hashes to identify the
        scenario source files associated with saved results.

        If the file contents remain unchanged, the hash
        should also remain unchanged.

        This test checks repeatability for one file.
        It does not verify that changing a file produces
        a different hash or that all experimental inputs
        are included in the provenance checks.
        """

        # Create a temporary directory for the test.
        #
        # The directory is isolated from the project's
        # actual data and results folders.
        #
        # The context manager automatically removes
        # the directory and its contents afterward.
        with tempfile.TemporaryDirectory() as directory:

            # Construct the path to a temporary text file.
            path = Path(directory) / "sample.txt"

            # Write a known string to the file.
            #
            # Using a fixed string gives the test
            # predictable file contents.
            #
            # UTF-8 explicitly specifies the text encoding.
            path.write_text("unchanged", encoding="utf-8")

            # Hash the same file twice and compare the results.
            #
            # digest() reads the file as bytes and calculates
            # its SHA-256 hexadecimal digest.
            #
            # Since the file is not modified between calls,
            # both hashes should be identical.
            #
            # This verifies deterministic hashing for
            # unchanged file contents.
            self.assertEqual(digest(path), digest(path))


# Run the test suite only when this file is executed directly.
#
# unittest.main() discovers and runs the test methods
# in ExperimentContractTests.
#
# It then reports the number of tests run, along with
# any failures or errors.
#
# Importing this file from another module does not
# automatically execute the test suite.
if __name__ == "__main__":
    unittest.main()
