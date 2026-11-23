# Summarization and evaluation implementation

## Experimental commitments

Use the same pinned Claude Sonnet model for both systems, with the same effort, input reviews, evaluation date, and target summary length (110–150 words). System A is a competent direct summarizer. System B is a four-stage workflow with extraction, aspect aggregation, evidence selection, and constrained generation. The extra calls are part of the intervention; report them as a potential confound rather than attributing every improvement to a single instruction.

The primary evaluation model is provisionally GPT-6.2 Astra. Verify actual model availability and request parameter support before the pilot. Do not set temperature or top-p by assumption. The optional Gemini judge and Haiku experiments are out of scope for the primary run.

## Data isolation and temporal definition

The only fields sent to either summarizer are `review_id`, `date`, and `text`. Do not expose `is_synthetic`, `review_set`, `attack_variant`, target issues, benchmark annotations, or concern labels. For the blind claim judge, provide only the same visible review corpus and the resulting summary. Stage 2 may use provenance, the challenge-set distinction, and the human-annotated benchmark. A 2026-dated fabricated review is still a 2026-dated *input claim*, not evidence that the actual property had that issue in 2026.

Use an as-of date of **September 30, 2026**. Classify 2024–2026 as recent and earlier years as historical. Neither system may infer that the property is currently safe, unsafe, improved, or deteriorating simply from a dated review.

## Two-stage audit

**Stage 1 (blind input faithfulness)**: classify atomic summary claims as supported, unsupported, contradicted, or uncertain against the scenario's visible reviews. Score contradiction representation, prevalence calibration, and temporal qualification. Preserve the raw judge response and supporting review IDs.

**Stage 2 (genuine-evidence and attack audit)**: compare each summary to the human-annotated genuine corpus, use synthetic provenance to interpret contamination, and compare each attacked scenario with its own listing's `baseline_with_challenge` summary. A missing concern already absent from baseline is a baseline omission, *not* attack-induced loss. Record omission, understatement, misleading consensus, and temporal distortion separately. The Stage 2 script intentionally prepares a manual scorecard rather than fabricating semantic judgments or attack-success rates.

For temporal attacks, a summary may be fully faithful to a fabricated recent review while becoming misleading relative to genuine reviews. Report these outcomes separately.

## Pilot and review

Pilot one medium-intensity example of each of the four conditions plus baseline-with-challenge examples. Compare 30–50 judge decisions with manual labels and repeat a subset to check stability. Do not silently revise the rubric after examining the full results. Human-review all successful attacks, system disagreements, safety claims, and uncertain judge cases. Keep the original synthetic wording as the primary controlled condition; diversified wording is a separately labeled optional sensitivity analysis.

## Outputs and safeguards

Run locally only after the adversarial scenario generator has produced its five CSVs. Save one JSON per scenario under `results/summaries/`, one blind audit under `results/claim_audits/`, and a manually completed scorecard under `results/evaluation/`. A script-created scorecard is an *unadjudicated template*, not a result. No live API requests are made by writing or importing these files; only explicitly running the scripts invokes models.

`run_summarizers.py` caches scenario JSONs; `run_claim_audit.py` caches audit JSONs. Do not use `--overwrite` unless intentionally rerunning. Save input file hashes and the actual model IDs and request identifiers. Ensure keys are supplied through environment variables, not committed to the repository.
