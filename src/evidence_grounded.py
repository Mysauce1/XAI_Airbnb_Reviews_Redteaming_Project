"""
Generate an evidence-grounded Airbnb review summary (System B).

Rather than asking Claude to summarize all reviews directly, this
script separates summarization into four stages:

1. Evidence extraction:
   Extract specific statements from the supplied reviews, along
   with their review IDs, aspects, sentiments, and quotations.

2. Evidence validation and organization:
   Check that extracted quotations actually appear in the supplied
   reviews, then organize the accepted evidence into an aspect-level
   ledger with sentiment counts and indicators of conflicting reports.

3. Evidence selection:
   Ask Claude to select which findings should appear in the summary,
   using the evidence ledger rather than the original review corpus.

4. Grounded summary generation:
   Generate the final summary from the selected claims, retaining
   citations and intermediate outputs for later auditing.

The evidence ledger is intended to make the summarization process
more transparent and reduce the risk of overlooking important
minority concerns, exaggerating consensus, or misrepresenting
historical issues as current.

Importantly, System B does not have access to the ground-truth
benchmark or labels identifying synthetic reviews. It processes
the same potentially manipulated review corpus as System A.

All extracted evidence is checked against the supplied reviews,
not against the authenticity of the reviews themselves. Therefore,
a quotation from a synthetic review can still pass validation.

This script makes Claude API calls and records the responses,
request IDs, and usage information for reproducibility and auditing.
"""

from __future__ import annotations

# Provides the defaultdict data structure, which automatically creates
# empty collections when a new dictionary key is encountered.
# Used below to group evidence by aspect and track unique review IDs.
from collections import defaultdict

# Provides utilities for loading prompt templates and converting
# Python data into the project's standardized JSON representation.
from experiment_common import prompt, canonical

# Wrapper for requesting structured JSON responses from Claude.
# Each call returns the parsed response, raw response, request ID,
# and usage information.
from model_clients import claude_json


def build_evidence(reviews):
    """
    Generate an evidence-grounded summary from a collection of reviews.

    Parameters
    ----------
    reviews : list[dict]
        Reviews supplied to the summarization system.

        Each review is expected to contain at least:
        - review_id: Identifier used to trace evidence to its source.
        - text: Original review text supplied to the model.

        Depending on the scenario, this collection may contain
        genuine reviews, synthetic reviews, or both.

    Returns
    -------
    dict
        Contains the generated summary, citations, evidence ledger,
        selected claims, rejected evidence, raw model responses,
        request IDs, and API usage information.

    Notes
    -----
    The function does not use ground-truth annotations to determine
    which reviews or statements are genuine.

    Its evidence checks establish whether extracted quotations are
    traceable to the input corpus, not whether the underlying
    statements are factually true.
    """

    # Stage 1: Extract evidence from the supplied reviews.

    # Divide the reviews into batches of 15 before sending them to Claude.
    #
    # Smaller batches help control the amount of input and output
    # processed in a single request, reducing the likelihood of
    # oversized or truncated JSON responses.
    #
    # The loop below processes every review, including any final
    # batch containing fewer than 15 reviews.
    batch_size = 15

    # Collect extracted evidence from every batch into one list.
    items = []

    # Preserve the raw extraction response from each API call.
    # These responses can be inspected if an extraction result
    # appears incomplete or inconsistent.
    extraction_responses = []

    # Store request IDs so individual API calls can be traced.
    extraction_request_ids = []

    # Record usage information for each extraction request.
    # This can be used later to examine token consumption and costs.
    extraction_usage = []

    # range() advances through the reviews in increments of batch_size.
    # Slicing selects the reviews included in the current batch.
    for start in range(0, len(reviews), batch_size):
        batch = reviews[start : start + batch_size]

        # Report progress because a scenario may require multiple
        # extraction requests and take some time to complete.
        print(
            f"  Extracting evidence from reviews "
            f"{start + 1}-{start + len(batch)} of {len(reviews)}"
        )

        # Send the current batch to Claude using the extraction prompt.
        #
        # prompt() loads the instructions for extracting evidence.
        # canonical() serializes the batch in a consistent format.
        #
        # max_tokens limits the number of output tokens available
        # for the structured extraction response.
        #
        # Claude receives the review text and associated input fields.
        # It does not receive the benchmark's ground-truth labels.
        extraction, raw, request_id, usage = claude_json(
            prompt("evidence_extraction.txt"),
            canonical({"reviews": batch}),
            max_tokens=8000,
        )

        # The extraction prompt is expected to produce an "evidence"
        # field containing a list of extracted statements.
        #
        # An absent field defaults to an empty list. The type check
        # catches cases where the field exists but has the wrong form.
        batch_items = extraction.get("evidence", [])

        if not isinstance(batch_items, list):
            raise ValueError("Expected an evidence list")

        # Add this batch's evidence to the combined collection.
        items.extend(batch_items)

        # Preserve the response and request metadata for auditing.
        extraction_responses.append(raw)
        extraction_request_ids.append(request_id)
        extraction_usage.append(usage)

    # Stage 2: Validate and organize the extracted evidence.

    # Create a lookup connecting each review ID to its supplied text.
    #
    # Converting IDs to strings makes comparisons consistent when
    # model-generated JSON represents IDs as strings rather than numbers.
    #
    # The lookup is built from the input reviews, so it includes
    # synthetic reviews if they were injected into the scenario.
    review_lookup = {str(r["review_id"]): r["text"] for r in reviews}

    # Separate evidence that passes validation from evidence
    # that must be rejected.
    valid_items = []
    rejected_items = []

    # Defensive check that the combined extraction result is a list.
    # In the current implementation, items is initialized as a list
    # and extended only with lists, so this is an additional safeguard.
    if not isinstance(items, list):
        raise ValueError("Expected evidence list")

    # Validate each extracted evidence item independently.
    #
    # This prevents an invalid quotation or review reference
    # from automatically entering the evidence ledger.
    for item in items:

        # Retrieve the fields needed to verify the evidence.
        review_id = str(item.get("review_id"))
        sentiment = item.get("sentiment")
        quote = item.get("quote")

        # None indicates that no validation problem has been found.
        reason = None

        # An extracted statement must refer to a review that was
        # actually included in the scenario input.
        if review_id not in review_lookup:
            reason = "Unknown review ID"

        # Only the four sentiment categories used by the project
        # are accepted. Unexpected labels are rejected.
        elif sentiment not in (
            "positive",
            "negative",
            "mixed",
            "neutral",
        ):
            reason = "Invalid sentiment"

        # A valid evidence item must contain a nonempty quotation.
        elif not isinstance(quote, str) or not quote.strip():
            reason = "Missing or invalid quotation"

        # Require the extracted quotation to appear exactly in the
        # corresponding review text.
        #
        # This helps prevent Claude from inventing or paraphrasing
        # evidence while presenting it as a direct quotation.
        #
        # Because this is a literal substring comparison, differences
        # in capitalization, punctuation, or whitespace can cause
        # otherwise legitimate quotations to be rejected.
        elif quote not in review_lookup[review_id]:
            reason = "Quotation does not appear verbatim in review"

        # Keep a record of rejected evidence and why it failed.
        # Accepted evidence is retained for the next stage.
        if reason:
            rejected_items.append(
                {
                    "review_id": review_id,
                    "reason": reason,
                    "quote": quote,
                }
            )
        else:
            valid_items.append(item)

    # Report how much extracted evidence passed validation.
    # This provides a quick indication of extraction quality.
    print(
        f"  Evidence validation: {len(valid_items)} accepted, "
        f"{len(rejected_items)} rejected"
    )

    # Print the rejection reasons without displaying the
    # complete rejected quotations.
    for rejected in rejected_items:
        print(f"    Rejected review {rejected['review_id']}: " f"{rejected['reason']}")

    # Stop rather than generating a summary without any
    # successfully validated evidence.
    if not valid_items:
        raise ValueError("No valid evidence remained after validation")

    # Continue using only the evidence that passed validation.
    items = valid_items

    # Organize evidence by aspect and sentiment.
    #
    # counts[aspect][sentiment] stores a SET of review IDs.
    # Using sets ensures that multiple quotations from one review
    # do not artificially increase the number of reviews
    # expressing a particular sentiment.
    #
    # evidence_by_aspect stores the actual evidence items,
    # including quotations, for later selection and auditing.
    counts = defaultdict(lambda: defaultdict(set))
    evidence_by_aspect = defaultdict(list)

    for item in items:
        aspect = str(item["aspect"])
        sentiment = item["sentiment"]
        rid = str(item["review_id"])

        # Count each review at most once per aspect and sentiment.
        counts[aspect][sentiment].add(rid)

        # Preserve all accepted evidence items, even when multiple
        # quotations come from the same review.
        evidence_by_aspect[aspect].append(item)

    # Build an evidence ledger containing one entry per aspect.
    #
    # Each entry includes sentiment counts, an indicator of
    # conflicting reports, and the underlying evidence.
    ledger = []

    # Sorting produces a consistent aspect order across runs.
    for aspect, evidence in sorted(evidence_by_aspect.items()):

        # Convert the sets of review IDs into numerical counts.
        #
        # These counts represent unique reviews expressing each
        # sentiment about this aspect, not numbers of quotations.
        sentiments = {
            s: len(counts[aspect][s])
            for s in (
                "positive",
                "negative",
                "mixed",
                "neutral",
            )
        }

        # Identify aspects containing both favorable and
        # unfavorable evidence.
        #
        # A conflict is recorded when at least one review contains
        # positive evidence and at least one contains negative
        # or mixed evidence.
        #
        # This does not prove that the reviews contradict each
        # other. It signals that the evidence-selection stage
        # should consider differing experiences.
        #
        # Mixed evidence alone does not activate this flag unless
        # positive evidence is also present.
        ledger.append(
            {
                "aspect": aspect,
                "sentiment_review_counts": sentiments,
                "has_conflict": bool(
                    sentiments["positive"]
                    and (sentiments["negative"] + sentiments["mixed"])
                ),
                "evidence": evidence,
            }
        )

    # Stage 3: Select evidence for the final summary.

    # Ask Claude to select the most relevant findings from
    # the validated, aspect-organized evidence ledger.
    #
    # The selection prompt can use the sentiment distributions,
    # conflicting evidence, and individual quotations to decide
    # which claims deserve attention.
    #
    # The as_of date and recent_years define the temporal
    # reference used by this experiment. They help the model
    # distinguish older reports from recent ones.
    #
    # The selection model receives the ledger, not the
    # original ground-truth benchmark.
    selected, raw_select, select_id, usage_select = claude_json(
        prompt("evidence_selection.txt"),
        canonical(
            {
                "as_of": "2026-09-30",
                "recent_years": [2024, 2025, 2026],
                "review_count": len(reviews),
                "ledger": ledger,
            }
        ),
        max_tokens=7000,
    )

    # Check that selected claims reference reviews represented
    # in the validated evidence ledger.
    #
    # This prevents the selection stage from citing a review
    # that contributed no accepted evidence.
    #
    # The check verifies review-ID membership only. It does not
    # establish that the selected claim is fully supported by
    # the cited quotation or that the review is authentic.
    allowed = {str(item["review_id"]) for item in items}

    for claim in selected.get("selected_claims", []):
        for rid in claim.get("review_ids", []):
            if str(rid) not in allowed:
                raise ValueError("Selected evidence ID missing from ledger")

    # Stage 4: Generate the evidence-grounded summary.

    # Generate the final summary using the selected claims.
    #
    # Unlike conventional summarization, this generation step
    # receives the selected evidence rather than the full
    # original review corpus.
    #
    # The intended benefit is to make the final summary depend
    # on an explicit, inspectable evidence-selection process.
    #
    # However, any incorrect or misleading evidence that survives
    # extraction and selection can still influence the summary.
    summary, raw_summary, summary_id, usage_summary = claude_json(
        prompt("grounded_generation.txt"),
        canonical(
            {
                "as_of": "2026-09-30",
                "selected_claims": selected.get("selected_claims", []),
                "review_count": len(reviews),
            }
        ),
        max_tokens=2400,
    )

    # Require the generated response to contain a summary string.
    # This checks the expected data type but does not independently
    # evaluate the summary's accuracy or completeness.
    if not isinstance(summary.get("summary"), str):
        raise ValueError("Missing summary")

    # Return the final summary together with the intermediate
    # evidence and model metadata.
    #
    # Keeping these records makes it possible to investigate:
    # - Which evidence was extracted from the input reviews.
    # - Which extracted statements failed validation.
    # - Which aspects and sentiments appeared in the ledger.
    # - Which claims were selected for inclusion.
    # - What the model produced at each stage.
    #
    # This is particularly important for the red-teaming study,
    # where a summary may be consistent with the manipulated
    # input corpus but misleading relative to genuine reviews.
    return {
        # Final summary text and citations returned by Claude.
        "summary": summary["summary"],
        "citations": summary.get("citations", []),
        # Complete validated evidence ledger and selection output.
        "ledger": ledger,
        "selection": selected,
        # Evidence excluded during quotation and metadata checks.
        "rejected_evidence": rejected_items,
        # Raw responses from the three Claude request stages.
        # Extraction can contain multiple responses because
        # the reviews are processed in batches.
        "raw_responses": {
            "extraction": extraction_responses,
            "selection": raw_select,
            "generation": raw_summary,
        },
        # API request identifiers for tracing individual calls.
        "request_ids": {
            "extraction": extraction_request_ids,
            "selection": select_id,
            "generation": summary_id,
        },
        # Usage information retained separately for each stage.
        "usage": {
            "extraction": extraction_usage,
            "selection": usage_select,
            "generation": usage_summary,
        },
    }
