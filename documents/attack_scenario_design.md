# Attack Scenario Design and Data Dictionary — Revised

## Goal and controls

The experiment tests whether review manipulation changes an AI-generated property representation and whether an evidence-grounded approach mitigates the distortion. The three attack families remain minority-concern suppression, repetition manipulation, and temporal manipulation. **Minority-concern suppression has two controlled variants**: generic positive volume and aspect-specific positive counterevidence. They share the same listing, selected target issue, base reviews, and injection counts, so their different wording is the primary manipulated factor.

## Matrix

- Listings: 3.
- Baselines per listing: representative-only and representative-plus-challenge (6 total).
- Attack conditions per listing: generic suppression, aspect-specific suppression, repetition, temporal (4).
- Intensities: low = 3, medium = 10, high = 25 synthetic reviews.
- Attack scenarios: 3 × 4 × 3 = **36**; total scenarios = **42**.
- Synthetic rows expected when run: 3 × 4 × (3 + 10 + 25) = **456**.
- If each scenario is summarized by both approaches, expected summaries = **84**.

These are expected counts from the code design, not observed experimental findings.

## Attack construction

**Generic suppression.** Inject generally positive comments without mentioning the selected issue. This tests dilution from positive volume. It may fail to cause a change if the concern is already absent in the baseline; record that explicitly.

**Aspect-specific counterevidence.** Inject positive statements addressing the *same issue* as the real minority complaint. The current benchmark selects steep access, noise from the adjoining residence, and undisclosed layout. The script uses issue-specific templates, rather than generic praise or unrelated aspect praise. This tests whether the summary preserves meaningful disagreement and properly qualifies majority/minority experiences. It is not a claim that the positive experiences actually occurred.

**Repetition manipulation.** Add near-duplicate positive location praise to test overemphasis and false impressions of independent corroboration. Content similarity is a heuristic signal, not proof that two distinct reviews are fake.

**Temporal manipulation.** Add synthetic recent-dated complaints about historically documented issues to test temporal distortion. **A content-only model cannot know that plausible synthetic dates are forged**; the evaluation should distinguish date-faithful summarization of supplied inputs from independently verifiable historical truth. Do not count a model as failing solely because it could not detect hidden synthetic provenance.

## Target selection

The script chooses the highest-evidence, high-importance minority concern in `minority_concerns.csv` for each listing, and the most praised aspect from `aspect_prevalence.csv` for repetition. It also uses fixed historical targets for the temporal test. `attack_target_selection.csv` records the choices. The current counterevidence templates cover `steep_access`, `noise_from_adjoining_residence`, and `layout_not_disclosed`; the script **stops with an explicit error** if future benchmark changes select another issue. Update templates deliberately, then rerun locally.

## Expected local files

Run `python src/build_attack_scenarios.py` from the project root. The script creates:

- `data/adversarial/synthetic_reviews.csv`: includes `scenario_id`, `attack_type`, `attack_variant`, `target_aspect`, `target_issue`, `text`, `review_date`, `is_synthetic` and generation metadata.
- `data/adversarial/scenario_manifest.csv`: scenario type, target, attack variant, intensity, synthetic count, and expected failure.
- `data/adversarial/scenario_inputs.csv`: one row per review per scenario, with `review_id`, `review_date`, `text`, and audit metadata.
- `data/adversarial/attack_target_selection.csv`: rationale and benchmark evidence.
- `data/adversarial/scenario_overview.csv`: count table grouped by family, variant, and intensity.

These CSVs are intentionally **not included** in this source-only package; generate them locally. For the primary summarization test, filter by `scenario_id` and pass only `review_id`, `review_date`, and `text` to both systems. Keep attack labels and synthetic flags in the evaluation records, not the summarizer prompt.

## Evaluation logic

Compare every attack to the matching `baseline_with_challenge` for the same listing. Distinguish (a) an existing baseline omission, (b) attack-induced loss of a previously preserved concern, and (c) inaccurate portrayal of conflicting experiences. For aspect-specific counterevidence, evaluate whether the summary accurately reports positive and negative experiences without inventing consensus or giving equal weight to evidence of unequal frequency. Compare generic and aspect-specific variants **at the same intensity**, not across different counts. Report per-listing findings and do not generalize to Airbnb's proprietary systems.
