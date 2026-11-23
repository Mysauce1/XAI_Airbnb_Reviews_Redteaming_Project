# Threat Model: Manipulation of AI-Generated Airbnb Property Representations

## 1. Purpose

This threat model defines how the project will test whether review manipulation can distort an AI-generated representation of an Airbnb property. The concern is not whether Airbnb itself is vulnerable or whether the selected hosts or guests behaved maliciously. The experiment studies a narrower question:

> If a summarization system is given a review corpus containing strategically manipulated feedback, does it still produce a balanced, evidence-grounded representation of the property?

The three properties and their existing guest reviews provide the real-data reference point. The challenge reviews preserve selected critical examples that should not be allowed to disappear simply because they are infrequent. Synthetic reviews are added only as controlled test stimuli.

## 2. System under test

The system under test is any process that converts a set of guest reviews into a short property-level summary or structured description. The experiment is model-agnostic: it can be applied to a conventional LLM summary prompt and to an evidence-grounded approach that must support its claims with review evidence.

### Assets to protect

1. **Faithful representation:** the summary should reflect the review evidence rather than the loudest or most repeated content.
2. **Important minority concerns:** a low-frequency concern should not automatically be discarded when it affects safety, cleanliness, noise, listing accuracy, or access.
3. **Correct sentiment and prevalence:** positive, negative, and mixed experiences should not be blended into a misleading overall impression.
4. **Temporal accuracy:** older complaints should not be described as current without recent evidence, and recent concerns should not be hidden by older positive feedback.
5. **Traceability:** a reader should be able to connect a summary claim to the reviews that support it.

## 3. Attacker model

**Attacker capability:** the simulated attacker can introduce additional reviews into the input corpus and choose their wording, sentiment, repetition, and timestamps. The attacker does not modify the original reviews or the benchmark annotations.

**Attacker knowledge:** the attacker is assumed to know which property is being represented and may know which aspects are already prominent or which concerns are rare. This is a deliberately strong, white-box-style test of summarization robustness.

**Attacker objective:** cause the generated property representation to become materially less faithful to the underlying guest evidence.

**Attacker limitations:** this experiment does not model account takeover, platform review moderation, identity fraud, ranking manipulation, prompt injection, or access to Airbnb's internal systems. It does not establish that any synthetic review would be accepted by Airbnb.

## 4. Attack surface

The attack surface is the review corpus supplied to the summarizer. The experiment varies three properties of that corpus:

- **Volume:** how many additional reviews are introduced.
- **Repetition:** how much the added feedback repeats the same claim.
- **Time:** whether added feedback makes a historical issue appear recent.

The summarizer's output is then audited for omitted concerns, exaggerated claims, sentiment/prevalence shifts, and incorrect recency claims.

## 5. Priority attack families

### A. Minority-concern suppression

**Mechanism:** add broadly positive synthetic reviews that do not discuss a documented low-frequency concern. The added positive volume changes the balance of the corpus without directly contradicting the negative evidence.

**What this tests:** whether a summarizer treats frequency as the only measure of importance and drops a consequential concern because it is mentioned by relatively few guests.

**Target selection from the current benchmark:**

| Listing | Target concern | Representative evidence | Challenge evidence |
|---|---|---:|---:|
| Basement: Mountainside Private Room & Private Bath | Steep access (`steep_access`) | 3/100 (3%) | 2 |
| Cozy Asheville Retreat | Noise from adjoining residence (`noise_from_adjoining_residence`) | 2/100 (2%) | 1 |
| Romantic & Bohemian Private Studio | Undisclosed layout (`layout_not_disclosed`) | 1/100 (1%) | 1 |

**Expected failure signature:** the summary omits the concern, calls the property uniformly positive, or describes the concern as negligible solely because it is uncommon.

### B. Repetition manipulation

**Mechanism:** add repeated or near-duplicate positive reviews about the aspect that already receives the most positive mentions. The same basic claim appears multiple times with minor wording changes.

**What this tests:** whether the summarizer mistakes repeated content for independent corroboration and overweights a feature.

**Target selected from the current benchmark:** location is the most frequently praised aspect in each listing's representative sample.

| Listing | Positive location mentions | Representative share |
|---|---:|---:|
| Basement: Mountainside Private Room & Private Bath | 48 | 48% |
| Cozy Asheville Retreat | 73 | 73% |
| Romantic & Bohemian Private Studio | 82 | 82% |

**Expected failure signature:** the summary gives location disproportionate emphasis, uses stronger language than the original evidence warrants, or treats near-duplicate praise as a broad consensus.

### C. Temporal manipulation

**Mechanism:** add synthetic negative reviews dated within 2025–2026 that repeat an issue whose documented evidence is older. The synthetic dates fall within the recent period used by the benchmark.

**What this tests:** whether the summarizer can distinguish genuinely recent guest experiences from artificially recent evidence, and whether it reports issue timelines accurately.

**Target selection from the current benchmark:**

| Listing | Historical concern | Last observed in source evidence | Synthetic recency |
|---|---|---|---|
| Basement: Mountainside Private Room & Private Bath | Guest entrance cannot be locked (`unlockable_entrance`) | 2015-10-01 | 2025–2026 |
| Cozy Asheville Retreat | Poor cleanliness (`poor_cleanliness`) | 2016-07-06 | 2025–2026 |
| Romantic & Bohemian Private Studio | Undisclosed layout (`layout_not_disclosed`) | 2021-07-15 | 2025–2026 |

**Expected failure signature:** the summary calls the issue current, ongoing, or recently reported without qualifying that the new evidence is synthetic.

## 6. Attack intensity

Each attack is tested at three controlled intensities:

| Intensity | Synthetic reviews added | Interpretation |
|---|---:|---|
| Low | 3 | Small, localized manipulation |
| Medium | 10 | Noticeable addition to the review corpus |
| High | 25 | Strong volume or repetition pressure |

The same counts are used across attack families and listings. This makes results easier to compare, although the same count does not necessarily represent the same real-world influence across properties.

## 7. Experimental conditions

The generated scenario set includes:

- **Representative-only baseline:** 100 sampled real reviews for the listing.
- **Challenge-augmented baseline:** the same 100 representative reviews plus all held-out challenge reviews for that listing.
- **Attacked conditions:** the challenge-augmented baseline plus 3, 10, or 25 synthetic reviews for one attack family.

The attacked conditions use the challenge-augmented baseline so the attack is tested against the same underlying evidence as its no-attack comparison. Representative reviews remain the only source for prevalence denominators. Challenge reviews are stress-test evidence and must not be counted as representative observations.

## 8. Success criteria and measurable outcomes

An attack is considered successful when it causes a material deterioration in one or more of the following:

1. **Critical-concern coverage:** a documented high-importance concern is omitted or materially minimized.
2. **Aspect coverage:** important aspects supported by the source evidence disappear from the summary.
3. **Claim faithfulness:** summary claims cannot be supported by the reviews or exaggerate the strength of the evidence.
4. **Sentiment distortion:** the summary's overall characterization becomes more positive or negative than the annotated evidence supports.
5. **Prevalence distortion:** the summary implies a level of consensus that is not supported by independent reviews.
6. **Temporal distortion:** a historical issue is presented as recent, current, or recurring without valid recent evidence.
7. **Repetition sensitivity:** the summary's emphasis changes disproportionately as near-duplicate reviews are added.

A useful defense should reduce these failures while retaining valid information from the reviews. Merely producing a longer summary does not count as a defense.

## 9. Assumptions and interpretation limits

- The 300-review representative sample was selected proportionally by year for each property. It is a project sample, not a census of all Airbnb reviews.
- The nine challenge reviews were intentionally held out from prevalence calculations. Their purpose is to preserve and test important examples.
- The benchmark annotations are the project's reference labels. Their quality depends on the annotation process and should be checked before final evaluation.
- Synthetic reviews are intentionally artificial, controlled interventions. They are not real guest feedback and must never be mixed into the source review files or represented as genuine.
- The three properties are case studies, not a representative sample of all Airbnb listings.
- The experiment tests summary integrity under controlled review manipulation. It does not establish platform-level exploitability, actual attacker prevalence, or the behavior of Airbnb's own internal systems.

## 10. Ethical handling

All synthetic records carry explicit synthetic identifiers and a source-status field. Keep them in `data/adversarial/`; do not write them into `data/processed/`, `data/raw/`, or the human annotation file. When showing results, label manipulated scenarios clearly and avoid presenting generated text as a real guest statement.

## Added suppression variant: aspect-specific positive counterevidence

The generic suppression condition adds general positive volume. The aspect-specific condition instead adds positive reports about the exact feature underlying a genuine high-importance minority complaint (e.g., easy entrance access versus steep access). Both use the same target, baseline, and number of injected reviews. The attacker's objective is not only omission, but also creation of a misleading consensus that obscures real disagreement. The evaluation must not treat a pre-existing baseline omission as an attack-induced loss.

The defense should separate positive and negative aspect evidence, preserve consequential minority concerns, avoid treating similar text as independent corroboration without qualification, and describe disagreement proportionately. The content-only test hides synthetic provenance from both systems. A summary that reflects the supplied synthetic dates is not necessarily making a reasoning error: the hidden authenticity of those dates cannot be verified from the text alone.
