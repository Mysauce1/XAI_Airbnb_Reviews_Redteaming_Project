"""
Check whether the local environment is ready to run the Airbnb
review-summarization experiments.

This script checks three things:
1. Whether the required Python packages are installed.
2. Whether the project files needed for the experiments exist.
3. Whether the Anthropic and OpenAI API keys appear to be configured.

These are preliminary setup checks only. The script does not make API
requests, verify that the keys are valid, or confirm model access.
It also does not print the API keys themselves.

Run from the project root:
    python src/check_setup.py
"""

from __future__ import annotations

# Used to check whether Python can locate an installed package
# without importing the package or running its code.
import importlib.util

# Provides access to environment variables, including API keys.
import os

# Makes it easier to construct file paths that work across
# different operating systems.
from pathlib import Path

# Loads variables from the project's .env file into the environment.
from dotenv import load_dotenv

# Find the project root based on where this script is saved.
# __file__ refers to this Python file, resolve() gets its full path,
# and parents[1] moves up two levels (from src/ to the project root).
#
# Using the script's location rather than the current working directory
# allows these file checks to work regardless of where the command is run.
ROOT = Path(__file__).resolve().parents[1]


# Load the API keys and other environment variables from .env.
# The .env file is expected to be located in the project root.
#
# By default, load_dotenv() does not overwrite environment variables
# that are already set. This allows existing environment settings
# to take precedence over values stored in the .env file.
#
# The script only reads these values; it does not display the keys.
load_dotenv(ROOT / ".env")


# Packages needed by the project's data-processing and AI workflows.
#
# pandas: Reads and processes the review datasets and evaluation files.
# anthropic: Provides access to the Claude models used for summarization.
# openai: Provides access to the OpenAI model used for evaluation.
# dotenv: Loads API credentials and configuration from the .env file.
#
# The checks below only determine whether Python can locate these
# packages. They do not verify package versions or functionality.
required_packages = [
    "pandas",
    "numpy",
    "matplotlib",
    "anthropic",
    "openai",
    "dotenv",
]


# Files that must exist before the relevant experiments can run.
# All paths are relative to the project root defined above.
#
# Processed data:
# - selected_reviews.csv contains the representative review samples.
# - challenge_reviews.csv contains additional reviews used to test
#   whether important concerns are preserved in summaries.
#
# Ground-truth benchmark:
# - minority_concerns.csv identifies concerns that may be mentioned
#   infrequently but are important for an accurate summary.
#
# Adversarial experiment inputs:
# - scenario_manifest.csv describes the baseline and attack conditions.
# - scenario_inputs.csv contains the reviews supplied to the models
#   for each scenario, including synthetic reviews where applicable.
#
# Prompts:
# - conventional.txt defines the standard summarization approach.
# - evidence_extraction.txt guides evidence extraction.
# - evidence_selection.txt guides which evidence is retained.
# - grounded_generation.txt guides evidence-based summary generation.
# - claim_judge.txt provides instructions for evaluating summary claims.
#
# This list is a setup checklist, not a complete inventory of every
# file that might be used elsewhere in the project.
required_files = [
    "data/processed/selected_reviews.csv",
    "data/processed/challenge_reviews.csv",
    "data/benchmark/minority_concerns.csv",
    "data/adversarial/scenario_manifest.csv",
    "data/adversarial/scenario_inputs.csv",
    "prompts/conventional.txt",
    "prompts/evidence_extraction.txt",
    "prompts/evidence_selection.txt",
    "prompts/grounded_generation.txt",
    "prompts/claim_judge.txt",
]


def main():
    """Run the package, file, and API-key configuration checks."""

    # Display a heading to make the console output easier to read.
    # No API requests are made during any of these checks.
    print("Checking local project setup (no API requests):")

    # Check whether each required Python package can be located.
    #
    # find_spec() looks for the package's import specification.
    # If it finds one, the package is reported as installed.
    # Otherwise, it is reported as missing.
    #
    # This does not guarantee that the package can be imported
    # successfully or that the installed version is compatible.
    for name in required_packages:
        print(
            f"  package {name}:",
            "installed" if importlib.util.find_spec(name) else "MISSING",
        )

    # Check whether each required project file exists.
    #
    # ROOT / name combines the project root with the relative path.
    # is_file() returns True only when that path points to a file.
    #
    # A file being present does not necessarily mean its contents
    # are complete, correctly formatted, or suitable for the experiment.
    for name in required_files:
        print(f"  file {name}:", "present" if (ROOT / name).is_file() else "MISSING")

    # Check whether both API-key environment variables have values.
    #
    # os.getenv() retrieves the variable without printing its contents.
    # If the variable does not exist, an empty string is returned.
    #
    # A key is considered configured when:
    # 1. Its value is not empty.
    # 2. Its value does not begin with 'replace_with', which is
    #    treated as a placeholder rather than a real credential.
    #
    # This is only a basic configuration check. An invalid, expired,
    # or unauthorized key could still be reported as configured.
    for name in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        value = os.getenv(name, "")

        print(
            f"  {name}:",
            (
                "configured"
                if value and not value.startswith("replace_with")
                else "NOT CONFIGURED"
            ),
        )

    # Clarify the limitations of the checks so that a successful
    # setup report is not mistaken for confirmation that the
    # project's API requests or model calls will work.
    print("This checks presence only, not API validity or model access.")


# Run the checks only when this file is executed directly.
#
# If another Python script imports this module, main() will not run
# automatically. This prevents setup messages from appearing simply
# because the module was imported.
if __name__ == "__main__":
    main()
