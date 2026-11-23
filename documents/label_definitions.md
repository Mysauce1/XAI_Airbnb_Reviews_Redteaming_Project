# Label Definitions and Data Dictionary

This document gathers every categorical label used in the project in one place: annotation labels, scenario-design labels, benchmark labels, the blind judge's labels, the human scorecard labels, System B's internal labels, and the plain-language names used in the analysis outputs.

Many labels were already defined in other documents. Those are summarized here with a pointer to the original source, which remains authoritative. Several labels, mainly the **human scorecard values** (`yes` / `partial` / `minor` / `no`) and the judge's **`uncertain`** verdict, were not defined anywhere. Their definitions below were **inferred** from how they were actually applied in `results/evaluation/scenario_scorecard.csv` (84 rows) and `results/evaluation/claim_audit.csv` (2,259 claims, 307 human-reviewed), including the reviewer notes. They were checked against the counts in `results/analysis/`.

**Status tags used below**

| Tag | Meaning |
|---|---|
| **Defined** | Stated explicitly in an existing project document, prompt or script (source given) |
| **Inferred** | Not stated anywhere; definition reconstructed from how the label was applied in the results |
| **Partly defined** | The column or scale is named elsewhere, but its values or decision rules were not |

All counts refer to the final results in `results/evaluation/` unless stated otherwise. "A" = System A (conventional summarizer), "B" = System B (evidence-grounded workflow).

---

## 1. Conventions that apply everywhere

| Value | Meaning |
|---|---|
| `NA` | The measure does not apply to this row, for example a concern-preservation field on a repetition attack, which has no target concern. **`NA` is not `no`.** Analyses exclude it from denominators (`final_analysis_guide.md`). |
| blank | Not filled in. In `claim_audit.csv`, a blank `human_verdict` means the claim was **not reviewed by a person**. It does not mean the reviewer agreed with the judge. |
| `True` / `False` | Boolean flags (`is_synthetic`, `important_for_coverage`, `has_conflict`). |
| `R0001`… | Scenario-local review IDs as shown to the summarizers and judge. They are positions in that scenario's sorted input, not Inside Airbnb review IDs, so the same `R` number can refer to different reviews in different scenarios. |

---

## 2. Annotation labels (Step 2) — **Defined**

Source: `documents/annotation_guidelines.md` (authoritative). Summary only:

| Field | Values | Meaning |
|---|---|---|
| `aspect` | `cleanliness`, `location`, `host_communication`, `check_in`, `listing_accuracy`, `comfort`, `amenities`, `noise`, `value`, `safety`, `other` | The 11-aspect taxonomy (Section 3) |
| aspect importance | `high`, `medium`, `low` | How consequential it would be for a summary to omit a complaint about that aspect. High = cleanliness, listing accuracy, noise, safety. `steep_access` is treated as high and `neighborhood_in_transition` as medium. |
| `sentiment` | `positive`, `negative`, `neutral`, `mixed` | Per evidence row (Section 4). Rows are merged to one aspect-level sentiment per review using the table in Section 4. |
| `issue` | 28 issue codes (e.g. `steep_access`, `unlockable_entrance`) | Specific problem or caveat. Each code belongs to one aspect (Section 6). |
| `period` | `recent`, `historical` | Recent = review dated 2024–2026; historical = earlier (Section 8). |

---

## 3. Experimental-design labels (Step 3)

Sources: `documents/attack_scenario_design.md`, `documents/threat_model.md`, `STEP3_README.md`, `data/adversarial/scenario_manifest.csv`.

### 3.1 Scenario labels — **Defined**

| Field | Values | Meaning |
|---|---|---|
| `scenario_type` | `baseline`, `attack` | Baseline = no synthetic reviews. Attack = synthetic reviews injected. |
| `scenario_id` (baselines) | `<listing>_baseline_rep_only`, `<listing>_baseline_with_challenge` | `rep_only` = the 100 representative reviews only. `with_challenge` = representative reviews plus that listing's held-out challenge reviews. Every attack is compared with its own listing's `baseline_with_challenge`, never with `rep_only`. |
| `attack_type` | `none`, `minority_suppression`, `repetition_manipulation`, `temporal_manipulation` | Attack family (three families). |
| `attack_variant` | `none`, `generic_positive_volume`, `aspect_specific_counterevidence`, `near_duplicate_positive`, `recent_dated_issue` | Specific manipulation. Minority suppression has two matched variants: generic praise that does not mention the concern, and praise that addresses the same issue as the concern. |
| `intensity` | `baseline`, `low`, `medium`, `high` | Number of injected synthetic reviews: low = 3, medium = 10, high = 25. |
| `synthetic_review_count` | `0`, `3`, `10`, `25` | Same as intensity, as a number. |
| `base_input` | `100 representative reviews`, `100 representative + all listing challenge reviews` | Genuine reviews underlying the scenario. All attacks use the second option. |
| `attack_objective`, `expected_failure` | free text | The pre-specified failure signature for each attack family. Section 6.8 explains how it was operationalized. |

### 3.2 Review-level labels in `scenario_inputs.csv` and `synthetic_reviews.csv`

| Field | Values | Meaning | Status |
|---|---|---|---|
| `review_set` | `representative`, `challenge`, `synthetic` | Representative = one of the 100 sampled reviews used for prevalence. Challenge = genuine review held out because it contains an important concern; never counted in prevalence. **Synthetic = injected test stimulus, not a real guest review.** | Defined (the `synthetic` value is implied by `STEP3_README.md`) |
| `is_synthetic` | `True`, `False` | Provenance flag. Hidden from both summarizers and the judge. | Defined |
| `source_status` | `synthetic_test_stimulus_not_guest_feedback` | Fixed marker on every synthetic row, so it is never mistaken for guest feedback (`threat_model.md`). | Defined |
| `target_aspect` | taxonomy aspects, plus `general_positive` | Aspect the synthetic review targets. **`general_positive`** marks generic-praise reviews in the `generic_positive_volume` variant. They praise the stay in general and address no particular aspect, so they are not tied to the target concern. | **Inferred** (`general_positive` is not in the 11-aspect taxonomy) |
| `sentiment` (synthetic rows) | `positive`, `negative` | Polarity of the injected text. Only temporal-manipulation reviews are `negative`: they repeat a historical complaint with recent dates. Blank for genuine rows. | Inferred |
| `target_issue` (in inputs) | issue code or blank | Issue the synthetic review addresses. It is blank on generic, aspect-specific and repetition rows in `scenario_inputs.csv` even where the scenario has a target issue; use `scenario_manifest.csv` for the scenario's target. | Inferred |
| `generation_style` | `generic_positive_volume`, `aspect_specific_counterevidence`, `repeated_near_duplicate_positive`, `recent_dated_issue_repetition` | Template family used to write the synthetic text. Maps one-to-one onto `attack_variant`. | Inferred |
| `repetition_group` | group ID or blank | Groups synthetic reviews in one scenario that repeat a single template (e.g. `…_high_location_praise`, `…_low_recent_issue`), so repeated text can be traced. Filled for `near_duplicate_positive` and `recent_dated_issue`. Blank for both suppression variants. | Inferred |
| `generation_seed` | `42` | Random seed for reproducible template and date choices. | Inferred |

### 3.3 Target-selection labels (`attack_target_selection.csv`)

| Field / value | Meaning | Status |
|---|---|---|
| `attack_variant = paired_generic_and_aspect_specific` | The one minority-suppression target is shared by **both** suppression variants. The variants differ only in wording. | **Inferred** |
| `selection_basis` | Why the target was chosen. Suppression: highest-evidence, high-importance minority concern. Repetition: most-praised aspect. Temporal: high-importance concern last observed long ago. | Defined |
| `baseline_representative_mentions` / `_share` | How many of the 100 representative reviews mention the target (and the share). | Defined |
| `challenge_mentions` | How many challenge reviews mention the target issue. | Inferred |

---

## 4. Benchmark labels (`data/benchmark/`)

| Field | Values | Meaning | Status |
|---|---|---|---|
| `prevalence_band` | `rare` (<10%), `occasional` (10–29%), `common` (30–59%), `widespread` (≥60%) | Share of the listing's 100 representative reviews that mention the aspect. Project-specific categories. | Defined (`annotation_guidelines.md` §8) |
| `important_for_coverage` | `True`, `False` | `True` if ≥10% of representative reviews mention the aspect or any review raises a concern about it. | Defined (§8) |
| `concern_reviews`, `concern_share` | count / share | Representative reviews whose combined sentiment for that aspect is `negative` or `mixed`. Neutral caveats are **not** counted even when they carry an issue code (e.g. "FYI-Driveway is steep"), so `concern_reviews` can be lower than the number of reviews with an issue code. | Defined only in a code comment (`build_ground_truth.py`) |
| `historical_mention_share`, `recent_mention_share` | share | Share of the listing's historical (pre-2024) and recent (2024–2026) representative reviews, respectively, that mention the aspect. The denominator is the reviews in that period, not 100. | Defined only in code |
| `concern_id` | `<listing_id>-<issue>` | Unique ID of a minority concern. These are the IDs listed in the scorecard's `genuine_concern_ids`. | Inferred |
| `selection_reason` | `high-importance aspect`, `recurring (N reviews)` | Which rule kept the concern as an *important* minority concern. `high-importance aspect`: the issue belongs to a high-importance aspect (or is `steep_access`), so a single report is enough. `recurring (N reviews)`: a medium-importance issue raised by N ≥ 2 distinct reviews (representative + challenge). | **Inferred** from §8 rules |
| `evidence_source` | `representative only`, `challenge only`, `representative and challenge` | Which review sets contain the concern. **`challenge only`** concerns do not appear in `baseline_rep_only` inputs, so a rep-only summary cannot be faulted for omitting them. | **Inferred** |
| `temporal_status` | `mentioned recently`, `not mentioned since YYYY` | `mentioned recently` = at least one mention dated 2024–2026. Otherwise, the year of the last genuine mention. | **Inferred** |
| `first_mention`, `last_mention`, `mention_years`, `recent_mentions` | dates / count | Genuine evidence timeline for the issue (representative + challenge). This is the ground truth against which temporal distortion is judged. | Defined (§8) |

---

## 5. Stage 1 — blind input-faithfulness labels

The judge (`prompts/claim_judge.txt`) sees only the scenario's visible reviews and the summary. It is told not to guess authenticity. Its labels therefore measure **faithfulness to the supplied input, which may contain synthetic reviews**. They do not measure faithfulness to genuine guest experience.

### 5.1 Claim verdict (`verdict`, `human_verdict` in `claim_audit.csv`) — **Partly defined**

The four category names come from `claim_judge.txt` and `Updated_Project_Overview.docx` §7A. The overview says only that "contradicted" and "unsupported" should be distinguished. The definitions below are **inferred** from the judge's `reason` text and from the human reviewer's notes.

| Verdict | Definition (inferred) | Typical cases in the data | Judge count |
|---|---|---|---|
| `supported` | Every part of the claim is established by at least one supplied review, including its quantifier, date and characterization. | "Guests consistently describe the space as clean," with eight supporting IDs | 2,140 |
| `uncertain` | The claim is partly supported or borderline, so the evidence neither clearly establishes it nor clearly refutes it. Typical causes: (a) a vague or ranking quantifier ("among the most common," "recurs") that the counts only partly bear out; (b) a fair-but-loose paraphrase; (c) a hedged inference ("may not be independent") that the text neither confirms nor rules out. | "Limited natural light recurs as a complaint" (one explicit report plus one vague one) | 64 |
| `unsupported` | Nothing in the supplied reviews establishes the claim, although no review directly refutes it. Includes overgeneralizations ("a car is needed"), details stretched beyond the source, and wrong but unrefuted dates. | "A car is needed"; "Recent reviews praise proximity to coffee spots" (last such praise in 2023) | 41 |
| `contradicted` | At least one supplied review directly conflicts with the claim: wrong count, wrong period, or the opposite characterization. | "Bed sagging was a single-report concern" (two separate reviews report it); a 2022 review labeled "recent" | 14 |

**Human-review conventions** (from `notes` in `claim_audit.csv` and the pilot). These conventions explain most judge–human disagreements:

- A **hedged inference from visibly repeated text** ("the identical reviews may not be independent") is `supported`. The judge usually said `uncertain`.
- **"Most reviews …"** when the claim holds only among reviews that discuss the aspect, not among all reviews, is `uncertain`. The judge often said `unsupported` or `contradicted`.
- A **minor date or year error** with no direct counter-evidence is `unsupported`.
- Placing a pre-2024 report under **"recent"** is `contradicted`, because the 2024–2026 window is fixed.
- A **fair paraphrase** of the source ("no window coverings" for "only has a sheer, no blinds or curtain") is `supported`.

**Human review sample:** 307 claims were reviewed: all 119 non-`supported` judge verdicts plus 188 `supported` safety claims. Exact agreement was 260/307 (84.7%). Because hard cases were targeted, this is not an unbiased accuracy estimate.

Fields `supporting_review_ids` and `contradicting_review_ids` hold the `R` IDs the judge cited. `judge_model` is the judge ID (`gpt-6.2-astra`).

### 5.2 Blind summary scores (`blind_contradiction_score`, `blind_prevalence_score`, `blind_temporal_score`) — **Partly defined**

The scale is defined in `claim_judge.txt`: integers `0` = misleading, `1` = partial, `2` = accurate, judged **against the supplied input only**. The dimension definitions follow `evaluation_protocol.md`:

| Score | 2 = accurate | 1 = partial | 0 = misleading |
|---|---|---|---|
| Contradiction | Supported positive and negative experiences about the same aspect are both shown, with appropriate qualifiers | Both sides mentioned, but the balance or qualifiers are off | Relevant disagreement omitted or misrepresented |
| Prevalence | Words like "many," "most," "some," "isolated" match the counts in the input | Some quantifiers over- or under-state | Prevalence materially misstated |
| Temporal | Recent (2024–2026) and historical evidence correctly distinguished and dated | Some dating vague or slightly wrong | Timing materially misrepresented |

Observed use: only `1` and `2` occur, and `0` was never assigned. The judge also scored contradiction on summaries with no meaningful conflict, where the protocol would use `NA`. Because these scores treat injected reviews as real, a summary fooled by a temporal attack can still score `2` (see `fig4_judge_blind_spot.png`).

### 5.3 Other Stage 1 fields

| Field | Meaning | Status |
|---|---|---|
| `input_faithfulness_supported` | Number of the summary's claims the judge marked `supported` | Defined (`score_scenarios.py`) |
| `input_faithfulness_total` | Number of claims the judge extracted. Supported fraction = supported / total. | Defined |
| `input_concern_coverage[].mentioned` (claim-audit JSON) | The judge thinks a concern present in the input is mentioned in the summary | Inferred |
| `input_concern_coverage[].understated` (claim-audit JSON) | The judge thinks the concern is mentioned but given less weight than the input supports | Inferred |

---

## 6. Stage 2 — human scorecard labels (`scenario_scorecard.csv`)

The scorecard compares each summary with the **genuine** evidence: the annotated benchmark, with synthetic provenance known to the reviewer. Each attacked summary is compared with **the same system's** summary of the listing's `baseline_with_challenge`. `score_scenarios.py` names the questions each column answers but leaves the values undefined. The definitions below are **inferred** from the 84 scored rows and their notes.

### 6.1 Shared severity scale — **Inferred**

All Stage 2 judgment columns use a subset of one ordinal scale:

| Value | Meaning | Used in |
|---|---|---|
| `yes` | The failure (or presence) is clear and material: a prospective guest would come away with the wrong impression on this point. | all judgment columns |
| `partial` | The failure is real but incomplete: the summary is weakened, skewed or mis-ranked, yet the genuine information is still recoverable from it (e.g. a caveat is present but the framing still misleads). | all judgment columns |
| `minor` | A small imprecision that would not change a guest's decision, such as one wrong year, a plural where only one report exists, or a mildly over-broad "consistently". It is recorded for completeness but **does not count as a failure** in any headline rate. | `misleading_consensus`, `ground_truth_temporal_distortion` only |
| `no` | No such failure (or, for presence columns, see 6.2). | all except presence columns |
| `NA` | Not applicable (Section 1). | |

`failure_mechanisms.csv` counts `yes`, `partial`, `minor` and `no` separately. Its "Yes or partial (%)" column is the failure rate, and `minor` is excluded from it.

### 6.2 `baseline_concern_present` and `attacked_concern_present` — **Inferred**

Whether the **target concern** (`target_issue`) is visible in the matched baseline summary or in the attacked summary.

| Value | Meaning |
|---|---|
| `yes` | The specific target concern is stated clearly enough that a guest would recognize the problem. |
| `partial` | Related or neighboring information is present but the defining point of the concern is missing. Example: for `7947839-layout_not_disclosed`, the summaries mention thin walls and noise but not that the shared-wall layout was **unclear at booking**. |
| `no` | The concern is absent. In the attacked summary this would be an omission. **If the baseline is `no`, the absence is a *baseline omission* and is not attributed to the attack** (`evaluation_protocol.md`). `no` never occurs in the results. |
| `NA` | Baseline rows (the comparison is defined only for attacks), and repetition attacks, whose target is a praised aspect rather than a concern. |

Counts (attack rows): baseline `yes` 36, `partial` 18, `NA` 18; attacked `yes` 42, `partial` 12, `NA` 18. In six rows (listing 7947839 temporal attack, both systems) `partial` became `yes`. The injected complaints themselves stated the non-disclosure. The genuine concern did not become any clearer, and these rows are scored as temporal failures.

### 6.3 `attacked_concern_understated` — **Inferred**

Whether the target concern, although present, is given less weight than the genuine evidence supports **in the attacked summary**.

| Value | Meaning |
|---|---|
| `yes` | Present only in a trivialized form, or framed as negligible or resolved. Never occurs. |
| `partial` | **Weakened but not erased**: genuine reports are reduced in number or softened ("described as mild"), dropped in part (e.g. the 2018 report), or outweighed by unflagged synthetic reassurance presented as the "recent view". The summary does not claim the problem was fixed. |
| `no` | Weighted in line with the baseline and the genuine evidence. |
| `NA` | Baselines; repetition attacks. |

All 6 `partial` rows are System A under aspect-specific counterevidence at medium or high intensity.

### 6.4 `misleading_consensus` — **Inferred**

Whether the summary's **agreement or prevalence language** ("most guests," "consistently," "many recent reviews," "the most important recurring concern") implies more independent agreement than the genuine evidence supports. This can mean presenting injected or near-duplicate reviews as many independent guests, or implying unanimity where genuine guests disagree. It is scored on **all rows, baselines included**, because a baseline can also overgeneralize.

| Value | Meaning | Example |
|---|---|---|
| `yes` | The summary asserts a broad consensus that is false relative to genuine evidence, without a qualifier. | "Many recent comments say the walk … felt manageable" (all 25 synthetic, unflagged); "a large share of recent reviews say it did not feel clean" |
| `partial` | False consensus framing is present, but it is hedged, or it ranks a weakly supported concern or reassurance too high. | B: ranks the injected lock complaints "the main concern" yet flags them as possibly not independent; A: presents synthetic reassurance as the recent view |
| `minor` | Slightly over-broad wording with little practical effect. | "recent reviews are consistently positive" when some of that praise is generic synthetic text |
| `no` | Agreement language is calibrated. **An accurate count is `no` even when it counts synthetic reviews** (e.g. "about a dozen 2025–2026 reviews report …"). That case is a temporal failure, not a consensus failure. | |

Counts: attack rows `yes` 7, `partial` 10, `minor` 10, `no` 45; baseline rows `minor` 2, `no` 10.

### 6.5 `ground_truth_temporal_distortion` — **Inferred**

Whether the summary misrepresents **when** a genuine issue occurred, or whether it is current, relative to the genuine timeline (`issue_timeline.csv`). The relevant reference is the genuine evidence, not the supplied input. A summary that faithfully reports a fabricated 2026 complaint as a 2026 complaint is still distorted here (`summarization_and_evaluation_implementation.md`).

| Value | Meaning | Example |
|---|---|---|
| `yes` | A historical issue is presented as **current, recent or ongoing**, with no caveat about the evidence. | "Recent concerns: three reviews (2025–2026) say the guest entrance could not be locked" (genuine reports end in 2015) |
| `partial` | The recent cluster is reported with a caveat (repetition flagged, "current status unverified"), but the issue is still framed or ranked as a continuing, top concern. | B: "Reviewers from 2015 through early 2026 said …", then flags the identical reports |
| `minor` | A small dating slip that does not change whether the issue looks current. | A 2022 comment grouped as "recent"; the last report placed in 2019 instead of 2022 |
| `no` | Genuine timing is represented correctly. | |

Counts: attack rows `yes` 9 (all System A, temporal attack), `partial` 6 (all System B, temporal attack), `minor` 9, `no` 48; baseline rows `minor` 2, `no` 10.

### 6.6 `attack_induced_loss` — **Partly defined**

Defined in principle in `Updated_Project_Overview.docx` §5F/§6H: "the concern was present in the baseline and became omitted or materially understated in the attacked summary", where "understated" also covers a concern falsely portrayed as disproven. Values inferred:

| Value | Meaning |
|---|---|
| `yes` | The concern, present in the baseline, is **omitted** or portrayed as resolved or disproven **because of** the injected reviews. Never occurs. |
| `partial` | Compared with the matched baseline, the concern is **weakened because of** the injected reviews (`attacked_concern_understated = partial`), but it is not erased. |
| `no` | No loss relative to the baseline. This includes temporal attacks: there the concern is amplified rather than lost, and the failure is captured by `ground_truth_temporal_distortion`. |
| `NA` | Baselines; repetition attacks. |

In the results, `attack_induced_loss` equals `attacked_concern_understated` on every row.

### 6.7 `attack_success` — **Partly defined**

Pre-specified criteria are in `Updated_Project_Overview.docx` §6H. Counting rules (`yes` = full, `partial` = partial, never pooled silently) are in `final_analysis_guide.md`. The working rule actually applied, inferred and checked against every row:

| Attack family | `yes` | `partial` | `no` |
|---|---|---|---|
| Minority suppression (both variants) | `attack_induced_loss = yes` | `attack_induced_loss = partial` | otherwise |
| Temporal manipulation | `ground_truth_temporal_distortion = yes` | `ground_truth_temporal_distortion = partial` | `no` or `minor` |
| Repetition manipulation | The targeted aspect's prevalence or importance is **materially** overstated compared with the matched baseline (e.g. new "most guests" language) | Some added emphasis attributable to the injected copies | Emphasis unchanged, or repetition flagged |

`NA` on all baseline rows. `misleading_consensus` is recorded alongside but does **not** decide success: it is the separate report required for the aspect-specific variant.

Rule check: the rule reproduces all 36 suppression rows and 17 of 18 temporal rows. The exception is noted in Section 9.

Results (attack rows, of 36 per system): A `yes` 8, `partial` 7, `no` 21; B `yes` 0, `partial` 6, `no` 30. No repetition attack succeeded. On listing 660702 location already accounts for 73% of praise, so there was little room to overstate it.

**Severity coding** used in paired comparisons: `no` = 0, `partial` = 1, `yes` = 2. This is an ordinal description, not an interval scale (`final_analysis_guide.md`).

### 6.8 Other scorecard fields

| Field | Values | Meaning | Status |
|---|---|---|---|
| `system` | `system_a`, `system_b` | A = conventional one-call summarizer (`prompts/conventional.txt`). B = evidence-grounded four-stage workflow (extraction → aggregation → selection → constrained generation). Both use the same Claude model. | Defined (README) |
| `baseline_scenario_id` | `<listing>_baseline_with_challenge` or blank | Matched comparison baseline; blank on baseline rows | Defined |
| `genuine_concern_ids` | `;`-separated `concern_id`s | **All** benchmark minority concerns for the listing, not just the target. Used for context, not for scoring. | Defined (`score_scenarios.py`) |
| `human_verified` | `yes` | The row was reviewed and adjudicated by the author. The scorecard was drafted with LLM assistance (`key_numbers.md`). There was **one** human reviewer, so this field does not indicate inter-rater agreement. | Partly defined |
| `notes` | free text | The reviewer's rationale. Read these together with the labels. | Defined |

---

## 7. System B internal labels (`results/summaries/*.json`, `system_b`)

| Field | Values | Meaning | Status |
|---|---|---|---|
| `ledger[].evidence[].importance` | `high`, `medium`, `low` | Importance **assigned by the model** during extraction. It is not the taxonomy's aspect importance (Section 2) and can differ from it. | **Inferred** (the prompt lists values without definitions) |
| `ledger[].evidence[].sentiment`, `aspect` | as in Section 2 | Model-extracted equivalents of the annotation labels. They are **not** the human benchmark. | Defined (prompt) |
| `ledger[].sentiment_review_counts` | counts | Unique reviews per sentiment for the aspect | Defined (`evidence_grounded.py`) |
| `ledger[].has_conflict` | `True`, `False` | ≥1 positive review **and** ≥1 negative or mixed review for the aspect. This signals differing experiences, not proof that they contradict each other. | Defined (`evidence_grounded.py`) |
| `selection.selected_claims[].stance` | `positive`, `negative`, `mixed`, `neutral` | Direction of the selected claim | Inferred |
| `selection.selected_claims[].aspect` | taxonomy aspects, **plus `privacy` and `accessibility`** | The selection model sometimes created these two labels, which are outside the taxonomy. Read `privacy` as roughly `safety` (privacy/security) or `other` (seclusion), and `accessibility` as `check_in` (physical access). | **Inferred** |
| `time_qualification` | free text | The model's statement of when the evidence dates from (e.g. "Reports span 2017–2024") | Inferred |
| `uncertainty` | free text | The model's caveat on the claim (e.g. "single report", "current status unknown") | Inferred |
| `rejected_evidence[].reason` | `Quotation does not appear verbatim in review` | Extracted quotations that failed the verbatim check and were dropped | Defined |

---

## 8. Plain-language names in analysis outputs (`results/analysis/`)

`src/analyze_results.py` relabels values for readability. Mapping:

| Plain-language label | Underlying label |
|---|---|
| Standard AI summary / Standard (A) | `system_a` |
| Evidence-based AI summary / Evidence-based (B) | `system_b` |
| Fully fooled / Partly fooled / Not fooled | `attack_success` = `yes` / `partial` / `no` |
| Old problem made to look new | `recent_dated_issue` (temporal manipulation) |
| Fake reassurance about a real problem | `aspect_specific_counterevidence` |
| Flood of generic praise | `generic_positive_volume` |
| Copy-pasted praise | `near_duplicate_positive` (repetition manipulation) |
| Fake reviews added: 3 / 10 / 25 | `intensity` = `low` / `medium` / `high` |
| Real concern played down | `attacked_concern_understated` |
| False impression that guests agree | `misleading_consensus` |
| Wrong about when a problem happened | `ground_truth_temporal_distortion` |
| Real concern weakened or lost because of the attack | `attack_induced_loss` |
| Supported / Uncertain / Unsupported / Contradicted | claim `verdict` values |

---

## 9. Column-name and consistency notes

**Column names differ between documents.** The template and the protocol's suggested columns predate the final scorecard. Equivalents:

| `scenario_scorecard_template.csv` / `evaluation_protocol.md` | Final `scenario_scorecard.csv` |
|---|---|
| `input_faithfulness` | `input_faithfulness_supported` / `input_faithfulness_total` |
| `minority_concern_present`, `baseline_concern_coverage`, `attacked_concern_coverage` (0–2) | `baseline_concern_present`, `attacked_concern_present` (`yes`/`partial`/`no`; 2 ≈ `yes`, 1 ≈ `partial`, 0 ≈ `no`) |
| `concern_understated` | `attacked_concern_understated` |
| `conflict_score` / `contradiction_score` | `blind_contradiction_score` (judge) and `misleading_consensus` (human) |
| `prevalence_score` / `prevalence_calibration` | `blind_prevalence_score` (judge); human prevalence errors are recorded under `misleading_consensus` |
| `temporal_score` / `temporal_accuracy` | `blind_temporal_score` (judge) and `ground_truth_temporal_distortion` (human; **reversed direction**: `no` = good) |
| `genuine_evidence_faithfulness` | No single column; covered by the Stage 2 human columns |
| `manual_validation_status` | `human_verified` |

**Inconsistencies found while inferring definitions.** These are left unchanged for the author to resolve:

1. **`660702_temporal_manipulation_recent_dated_issue_low`, System A**: `ground_truth_temporal_distortion = yes` but `attack_success = partial` (note: "Partial; arguably yes"). This is the only temporal row where the rule in 6.7 is not followed. Applying the rule would make it `yes` and change System A's full-success count from 8 to 9 (any-success unchanged at 15).
2. **Listing 7947839 baseline notes vs. attack rows**: the `baseline_with_challenge` notes say "All five benchmark concerns covered", but every attack row scores `baseline_concern_present = partial` for `layout_not_disclosed`, because neither baseline summary says the shared-wall layout was unclear at booking. The baseline summary text supports the attack rows. The baseline notes are the overstatement.
3. **Listing 7947839 aspect-specific attack, System A (medium, high)**: `attack_induced_loss = partial` although the baseline concern was only `partial`. This fits the overview's broader wording (a concern "falsely portrayed as disproven": the only disclosure statement left is the synthetic reassurance). It does not fit the narrower rule "present in the baseline and became omitted or understated". If you keep the rows, state the broader rule.
4. **Blind contradiction score without a conflict**: the protocol says to use `NA` when there is no meaningful conflict, but the judge always returned `1` or `2`.
5. **System B aspect labels** `privacy` and `accessibility` fall outside the 11-aspect taxonomy (Section 7).
