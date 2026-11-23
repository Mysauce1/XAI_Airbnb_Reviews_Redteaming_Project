"""Offline final analysis for the Airbnb review-summarization red-team study.

Run from the repository root:  python src/analyze_results.py
Requires pandas, numpy and matplotlib. Makes no API calls and never modifies
its inputs. Writes:

  results/analysis/tables/   human-readable CSV tables
  results/analysis/figures/  poster-ready PNG figures
  results/analysis/key_numbers.md   headline numbers in plain language

All attack outcomes come from the human-reviewed scorecard. The blind judge's
scores are reported separately and are never used to decide attack success.
"""

# The analysis is entirely offline: these imports handle arithmetic, paths, CSV data, and plotting.
# `comb` is used for the exact sign-test calculation rather than an external statistics package.
from math import comb
from pathlib import Path
import re
import textwrap
import warnings

import numpy as np
import pandas as pd

# Configure Matplotlib before importing pyplot so chart creation does not require
# a desktop display. This is useful when running from a terminal or CI environment.
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# Resolve paths relative to this script, not the current shell directory.
# Because this file lives in src/, parents[1] is the repository root.
ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "results" / "evaluation"
OUT = ROOT / "results" / "analysis"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"

# These are input files. The script reads them but does not write to them.
# The scorecard supplies human-reviewed attack outcomes; claim_audit.csv supplies
# the sampled human-versus-judge claim comparisons. The manifest supplies labels.
SCORECARD = EVAL / "scenario_scorecard.csv"
CLAIMS = EVAL / "claim_audit.csv"
MANIFEST = ROOT / "data" / "adversarial" / "scenario_manifest.csv"
INPUTS = ROOT / "data" / "adversarial" / "scenario_inputs.csv"
CONCERNS = ROOT / "data" / "benchmark" / "minority_concerns.csv"

# Figures from earlier versions of this script; removed so they can't be mistaken for current output.
# Older chart filenames are listed so a rerun does not leave stale visuals
# that could be mistaken for figures from the current analysis.
OBSOLETE_FIGURES = [
    "attack_outcomes_by_system.png",
    "paired_system_comparison.png",
    "attack_response_by_intensity.png",
    "attack_heatmap_system_a.png",
    "attack_heatmap_system_b.png",
    "blind_faithfulness_attacks.png",
]

# ---------------------------------------------------------------- plain-language labels
# The ordered labels below control both CSV presentation and figure ordering.
# Internal codes are kept separate from presentation-friendly descriptions.
SYSTEMS = ["system_a", "system_b"]
SYSTEM_LABEL = {
    "system_a": "Standard AI summary (System A)",
    "system_b": "Evidence-based AI summary (System B)",
}
SYSTEM_SHORT = {"system_a": "Standard (A)", "system_b": "Evidence-based (B)"}
# Keep a fixed attack order across tables and plots, regardless of the order
# in which the experiment generated its scenarios.
ATTACKS = [
    "recent_dated_issue",
    "aspect_specific_counterevidence",
    "generic_positive_volume",
    "near_duplicate_positive",
]
ATTACK_LABEL = {
    "recent_dated_issue": "Old problem made to look new",
    "aspect_specific_counterevidence": "Fake reassurance about a real problem",
    "generic_positive_volume": "Flood of generic praise",
    "near_duplicate_positive": "Copy-pasted praise",
}
# Intensity names correspond to the number of synthetic reviews injected
# into a scenario: low=3, medium=10, high=25.
INTENSITIES = ["low", "medium", "high"]
INTENSITY_LABEL = {
    "low": "3 fake reviews",
    "medium": "10 fake reviews",
    "high": "25 fake reviews",
}
INTENSITY_NUMBER = {"low": 3, "medium": 10, "high": 25}
# Attack success is a three-level human judgment. It is NOT inferred from
# the blind judge's claim-support scores. A partial success is kept distinct.
OUTCOMES = ["yes", "partial", "no"]
OUTCOME_LABEL = {"yes": "Fully fooled", "partial": "Partly fooled", "no": "Not fooled"}
VERDICT_LABEL = {
    "supported": "Supported",
    "unsupported": "Unsupported",
    "contradicted": "Contradicted",
    "uncertain": "Uncertain",
}
# Claim verdicts are a different scale from attack outcomes: they describe
# whether individual summary statements are supported by the supplied reviews.
VERDICTS = ["supported", "uncertain", "unsupported", "contradicted"]
# Mechanism fields capture *how* a summary went wrong. These can overlap:
# a single scenario may involve both concern understatement and false consensus.
MECHANISM_LABEL = {
    "attacked_concern_understated": "Real concern played down",
    "misleading_consensus": "False impression that guests agree",
    "ground_truth_temporal_distortion": "Wrong about when a problem happened",
    "attack_induced_loss": "Real concern weakened or lost because of the attack",
}
LEVELS = ["yes", "partial", "minor", "no"]

# ---------------------------------------------------------------- figure style
# Reference palette from the dataviz skill (light mode, print). Outcome colours use the
# reserved status steps (critical / serious) plus a neutral grey for "nothing happened";
# every outcome also has its own marker shape and text label, so colour never works alone.
# Use a consistent print-friendly palette for all charts. Outcome colors
# are supplemented with shapes, text, and hatching for accessibility.
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
OUTCOME_COLOR = {"yes": "#d03b3b", "partial": "#ec835a", "no": "#898781"}
GENUINE = "#2a78d6"  # categorical slot 1
SYNTHETIC = "#eb6834"  # categorical slot 2
BETTER_B = "#2a78d6"
SAME = "#c3c2b7"

# Set plotting defaults once so each figure does not repeat font, axis,
# background, and border styling.
plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "text.color": INK,
        "axes.titlecolor": INK,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


# ---------------------------------------------------------------- helpers
# Load all columns as strings to preserve identifiers and human-entered
# categorical labels exactly. Disabling automatic NA conversion keeps values
# such as the literal "na" distinct from missing cells.
def load_csv(path):
    # Fail immediately with the missing filename rather than producing
    # partial analysis from an incomplete experiment.
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    return pd.read_csv(path, keep_default_na=False, dtype=str)


# Write one derived CSV to the analysis/tables directory and print its
# relative path so it is easy to find after the script finishes.
def save(df, name):
    path = TABLES / name
    df.to_csv(path, index=False)
    print(f"Wrote {path.relative_to(ROOT)} ({len(df)} rows)")


# Normalize category values before comparison: whitespace and capitalization
# should not change whether a human-reviewed field is recognized.
def normal(s):
    return s.astype(str).str.strip().str.lower()


# Percentages use the relevant observed denominator. If no observations
# are available, return NaN instead of dividing by zero.
def pct(num, den):
    return round(100 * num / den, 1) if den else np.nan


# Save the completed figure at print-friendly resolution and close it
# immediately to avoid accumulating open figures in memory.
def finish(fig, name):
    path = FIGURES / name
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {path.relative_to(ROOT)}")


# Place a consistent headline and explanatory subtitle in figure coordinates
# (rather than axes coordinates) so they align across different chart types.
def title_block(fig, title, subtitle, top=0.98, gap=0.06, x=0.01):
    """Title and subtitle anchored to the top-left of the figure."""
    fig.text(x, top, title, fontsize=15, fontweight="bold", ha="left", va="top")
    fig.text(x, top - gap, subtitle, fontsize=10.5, color=INK_2, ha="left", va="top")


# Format a statistical p-value for figure annotations. This is only
# descriptive here because scenarios share listings and are not independent.
def p_text(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.2g}"


# Represent the three attack outcomes with distinct fill patterns.
# The shape/fill conveys the category even in grayscale.
def outcome_marker(ax, x, y, outcome, size=13):
    """Filled = fully fooled, half-filled = partly fooled, hollow = not fooled."""
    color = OUTCOME_COLOR[outcome]
    style = {"yes": "full", "partial": "left", "no": "none"}[outcome]
    ax.plot(
        x,
        y,
        marker="o",
        markersize=size,
        linestyle="none",
        fillstyle=style,
        markerfacecolor=color if outcome != "no" else "none",
        markerfacecoloralt=SURFACE,
        markeredgecolor=color,
        markeredgewidth=2,
    )


# Create legend symbols that use exactly the same appearance as plotted dots.
def outcome_legend_handles(size=11):
    handles = []
    # Stack outcome categories from left to right and label each segment
    # with its count, including a patterned partial-success segment.
    for o in OUTCOMES:
        style = {"yes": "full", "partial": "left", "no": "none"}[o]
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markersize=size,
                fillstyle=style,
                markerfacecoloralt=SURFACE,
                markerfacecolor=OUTCOME_COLOR[o] if o != "no" else "none",
                markeredgecolor=OUTCOME_COLOR[o],
                markeredgewidth=2,
                label=OUTCOME_LABEL[o],
            )
        )
    return handles


# Compare paired systems using only scenarios where their ordinal outcomes
# differ. Under the null, either system is equally likely to do better.
# Because multiple scenarios reuse the same three listings, this p-value
# is exploratory rather than evidence from independent experimental units.
def sign_test(wins, losses):
    """Exact two-sided sign test on non-tied pairs."""
    # Ties provide no direction, so they are excluded from the binomial count.
    n = wins + losses
    if n == 0:
        return np.nan
    # The two-sided tail probability is twice the smaller binomial tail,
    # capped at 1 to remain a valid probability.
    k = min(wins, losses)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


# Build the same summary statistics for any grouping: system, attack
# variant, injection intensity, or listing. This avoids inconsistent
# denominators and duplicated aggregation logic.
def outcome_table(attack, by, rename):
    rows = []
    for key, g in attack.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        # Each row is one human-verified attacked summary for one system.
        n = len(g)
        full, part = int((g.outcome == "yes").sum()), int(
            (g.outcome == "partial").sum()
        )
        row = dict(zip(rename, key))
        # Report both strict success (fully fooled) and the broader rate that
        # includes partial success. The severity average uses no=0, partial=1, yes=2.
        row.update(
            {
                "Attack tests": n,
                "Fully fooled": full,
                "Partly fooled": part,
                "Not fooled": n - full - part,
                "Fully fooled (%)": pct(full, n),
                "Fully or partly fooled (%)": pct(full + part, n),
                "Average severity (0 = not fooled, 2 = fully fooled)": round(
                    g.severity.mean(), 2
                ),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- main
# Run the analysis in stages: validate inputs, aggregate attack outcomes,
# compare paired systems, examine blind-judge scores, assess human agreement,
# then create figures and a short Markdown summary.
def main():
    # Create output directories if this is the first run. Only derived analysis
    # outputs belong here; raw experiment files remain untouched.
    for folder in (TABLES, FIGURES):
        folder.mkdir(parents=True, exist_ok=True)
    # Delete only explicitly named outdated figures, not the whole folder.
    # This prevents misleading duplicates after revisions to the visualization.
    for name in OBSOLETE_FIGURES:
        if (FIGURES / name).exists():
            (FIGURES / name).unlink()
            print(f"Removed outdated figure {name}")

    # Read the full human-reviewed scorecard and the separate claim-audit sample.
    # The manifest provides scenario metadata and readable listing names.
    score = load_csv(SCORECARD)
    claims = load_csv(CLAIMS)
    manifest = load_csv(MANIFEST)
    # Check the scorecard schema before attempting any statistics.
    # A missing human-review field is a data-preparation issue, not a zero.
    required = [
        "scenario_id",
        "system",
        "scenario_type",
        "attack_variant",
        "intensity",
        "listing_id",
        "attack_success",
        "human_verified",
        "attacked_concern_understated",
        "misleading_consensus",
        "ground_truth_temporal_distortion",
        "attack_induced_loss",
        "input_faithfulness_supported",
        "input_faithfulness_total",
    ]
    missing = [c for c in required if c not in score.columns]
    if missing:
        raise ValueError(f"Scorecard missing columns: {missing}")
    # Each scenario must have at most one row per system. Duplicates
    # would otherwise inflate counts and break paired comparisons.
    if score.duplicated(["scenario_id", "system"]).any():
        raise ValueError("Duplicate scenario_id/system pairs in scorecard")
    # The manifest should define each scenario exactly once.
    if manifest.scenario_id.duplicated().any():
        raise ValueError("Duplicate scenario_id in manifest")
    # Warn about coverage differences; this check does not stop execution,
    # so investigate any warning before reporting final results.
    if set(score.scenario_id) != set(manifest.scenario_id):
        warnings.warn(
            "Scorecard and manifest scenario IDs differ; inspect before interpreting"
        )
    # Map listing IDs to human-readable names for tables and figures.
    listing_name = dict(zip(manifest.listing_id, manifest.listing_name))

    # Normalize coded fields and convert only numeric judge counts to numbers.
    # The raw CSV values remain strings until conversion is explicitly needed.
    for col in [
        "system",
        "scenario_type",
        "attack_variant",
        "intensity",
        "attack_success",
    ]:
        score[col] = normal(score[col])
    score["supported"] = pd.to_numeric(
        score.input_faithfulness_supported, errors="coerce"
    )
    score["total"] = pd.to_numeric(score.input_faithfulness_total, errors="coerce")
    print(
        f"Scorecard rows: {len(score)}; unique scenarios: {score.scenario_id.nunique()}"
    )
    print(f'Human-verified rows: {(normal(score.human_verified) == "yes").sum()}')
    print(f"Claim rows: {len(claims)}")

    # Baselines are excluded from attack-success denominators.
    # They are retained in `score` for the separate faithfulness comparison.
    attack = score[score.scenario_type == "attack"].copy()
    # Attack outcomes must be manually checked before they can be used
    # as the ground-truth-based endpoint of this study.
    if not (normal(attack.human_verified) == "yes").all():
        raise ValueError(
            "Some attack rows are not human_verified=yes; finish review first"
        )
    # Reject unrecognized outcome labels rather than silently treating them
    # as failures or dropping them from the analysis.
    unexpected = set(attack.attack_success) - set(OUTCOMES)
    if unexpected:
        raise ValueError(f"Unexpected attack_success values: {unexpected}")
    # Translate the categorical attack outcome into a 0–2 severity scale
    # solely for paired ordering and descriptive means; it is ordinal.
    attack["outcome"] = attack.attack_success
    attack["severity"] = attack.outcome.map({"no": 0, "partial": 1, "yes": 2})
    attack["System"] = attack.system.map(SYSTEM_LABEL)
    attack["Attack type"] = attack.attack_variant.map(ATTACK_LABEL)
    attack["Fake reviews added"] = attack.intensity.map(INTENSITY_NUMBER)
    attack["Listing"] = attack.listing_id.map(
        lambda x: f"{listing_name.get(x, x)} ({x})"
    )
    # Centralize presentation ordering for all tables, including the
    # numeric injection counts instead of alphabetical intensity names.
    order = {
        "System": [SYSTEM_LABEL[s] for s in SYSTEMS],
        "Attack type": [ATTACK_LABEL[a] for a in ATTACKS],
        "Fake reviews added": [3, 10, 25],
    }

    # Apply consistent category order to whichever grouping columns
    # exist in the current table, then reset the row index.
    def sort(df):
        for col, vals in order.items():
            if col in df:
                df[col] = pd.Categorical(df[col], categories=vals, ordered=True)
        return df.sort_values(
            [
                c
                for c in ["System", "Attack type", "Fake reviews added", "Listing"]
                if c in df.columns
            ]
        ).reset_index(drop=True)

    # 1. Attack outcomes (human-reviewed) ---------------------------------------
    # Produce five views of the human-reviewed outcome: overall by system,
    # by attack mechanism, by injection count, by listing, and the
    # variant-by-intensity interaction.
    save(
        sort(outcome_table(attack, ["System"], ["System"])),
        "attack_outcomes_by_system.csv",
    )
    save(
        sort(
            outcome_table(attack, ["System", "Attack type"], ["System", "Attack type"])
        ),
        "attack_outcomes_by_variant.csv",
    )
    save(
        sort(
            outcome_table(
                attack,
                ["System", "Fake reviews added"],
                ["System", "Fake reviews added"],
            )
        ),
        "attack_outcomes_by_intensity.csv",
    )
    save(
        sort(outcome_table(attack, ["System", "Listing"], ["System", "Listing"])),
        "attack_outcomes_by_listing.csv",
    )
    save(
        sort(
            outcome_table(
                attack,
                ["System", "Attack type", "Fake reviews added"],
                ["System", "Attack type", "Fake reviews added"],
            )
        ),
        "attack_outcomes_by_variant_intensity.csv",
    )

    # 2. Paired comparison: same scenario, both systems -------------------------
    # Pair the two systems by exact scenario ID, ensuring both received
    # the same injected reviews and genuine-review context.
    paired = attack.pivot(index="scenario_id", columns="system", values="severity")
    # Stop if either system is missing for any attacked scenario.
    # An unpaired comparison would not support the intended interpretation.
    if not set(SYSTEMS) <= set(paired.columns) or paired[SYSTEMS].isna().any().any():
        raise ValueError("Every attacked scenario needs a result for both systems")
    paired = paired.reset_index()
    # Positive A-minus-B severity means B was less fooled; negative means A
    # was less fooled. Zero means identical ordinal attack outcomes.
    paired["diff"] = paired.system_a - paired.system_b
    paired["Which did better"] = np.select(
        [paired["diff"] > 0, paired["diff"] < 0],
        ["Evidence-based (B) did better", "Standard (A) did better"],
        default="Same result",
    )
    # Attach scenario labels after pairing; drop duplicates because each
    # scenario has two system rows but should appear only once here.
    details = attack[
        ["scenario_id", "Listing", "Attack type", "Fake reviews added"]
    ].drop_duplicates()
    paired = paired.merge(details, on="scenario_id", how="left", validate="one_to_one")
    # Convert ordinal numeric outcomes back to plain English in the CSV.
    rev = {0: "Not fooled", 1: "Partly fooled", 2: "Fully fooled"}
    paired_out = paired.rename(columns={"scenario_id": "Scenario ID"}).assign(
        **{
            "System A result": paired.system_a.map(rev),
            "System B result": paired.system_b.map(rev),
        }
    )
    paired_out = sort(
        paired_out[
            [
                "Scenario ID",
                "Listing",
                "Attack type",
                "Fake reviews added",
                "System A result",
                "System B result",
                "Which did better",
            ]
        ]
    )
    save(paired_out, "paired_attack_comparisons.csv")
    # Count directional wins and ties, then compute an exploratory exact
    # sign test on the non-tied paired comparisons.
    b_better = int((paired["diff"] > 0).sum())
    a_better = int((paired["diff"] < 0).sum())
    ties = int((paired["diff"] == 0).sum())
    p_value = sign_test(b_better, a_better)
    save(
        pd.DataFrame(
            [
                {"Result": "Evidence-based (B) did better", "Attack tests": b_better},
                {"Result": "Same result", "Attack tests": ties},
                {"Result": "Standard (A) did better", "Attack tests": a_better},
                {
                    "Result": "Exact sign test, two-sided p (ties excluded; tests share 3 listings, so not fully independent)",
                    "Attack tests": f"{p_value:.2g}",
                },
            ]
        ),
        "paired_comparison_counts.csv",
    )

    # 3. Failure mechanisms: every graded level counted; only NA excluded --------
    rows = []
    for s in SYSTEMS:
        part = attack[attack.system == s]
        for m, label in MECHANISM_LABEL.items():
            vals = normal(part[m])
            # Exclude explicitly inapplicable assessments from the denominator;
            # do not treat NA as a negative finding.
            assessed = vals[vals != "na"]
            unknown = set(assessed) - set(LEVELS)
            if unknown:
                raise ValueError(f"Unexpected values in {m}: {unknown}")
            n = len(assessed)
            # Preserve the distinction among yes, partial, minor, and no,
            # rather than collapsing all non-no values into one category.
            counts = {lvl: int((assessed == lvl).sum()) for lvl in LEVELS}
            rows.append(
                {
                    "System": SYSTEM_LABEL[s],
                    "Failure type": label,
                    "Tests assessed (NA excluded)": n,
                    "Yes": counts["yes"],
                    "Partial": counts["partial"],
                    "Minor": counts["minor"],
                    "No": counts["no"],
                    "Yes (%)": pct(counts["yes"], n),
                    "Yes or partial (%)": pct(counts["yes"] + counts["partial"], n),
                }
            )
    save(pd.DataFrame(rows), "failure_mechanisms.csv")

    # 4. Blind judge: share of claims supported by the (possibly manipulated) input
    # The blind judge sees the reviews supplied to the summarizer, including
    # any injected reviews. Its support scores measure input faithfulness,
    # not whether a claim is true relative to genuine guest experiences.
    scen_label = {
        "attack": "Attacked (fake reviews added)",
        "baseline": "Baseline (no fake reviews)",
    }
    faith = []
    # Aggregate supported claims with a claim-weighted denominator:
    # sum(supported claims) / sum(all claims), not mean(per-summary percentages).
    for (s, t), g in score.groupby(["system", "scenario_type"]):
        faith.append(
            {
                "System": SYSTEM_LABEL[s],
                "Scenario type": scen_label.get(t, t),
                "Summaries": len(g),
                "Claims checked by judge": int(g.total.sum()),
                "Claims judged supported": int(g.supported.sum()),
                "Supported (%)": pct(g.supported.sum(), g.total.sum()),
            }
        )
    save(sort(pd.DataFrame(faith)), "blind_input_faithfulness.csv")

    # Calculate per-summary supported-claim proportions for a paired
    # faithfulness comparison. Zero-claim summaries are treated as missing.
    attack["faith"] = attack.supported / attack.total.replace(0, np.nan)
    fp = attack.pivot(
        index="scenario_id", columns="system", values="faith"
    ).reset_index()
    fp = fp.merge(details, on="scenario_id", how="left")
    fp_out = pd.DataFrame(
        {
            "Scenario ID": fp.scenario_id,
            "Listing": fp.Listing,
            "Attack type": fp["Attack type"],
            "Fake reviews added": fp["Fake reviews added"],
            "System A claims supported (%)": (100 * fp.system_a).round(1),
            "System B claims supported (%)": (100 * fp.system_b).round(1),
            "Difference, B minus A (percentage points)": (
                100 * (fp.system_b - fp.system_a)
            ).round(1),
        }
    )
    save(sort(fp_out), "paired_faithfulness.csv")

    # Judge score split by the human verdict on attack success (the "blind spot").
    # Cross-tabulate judge-supported claims against the human attack outcome.
    # This exposes cases where a summary can appear supported by the
    # manipulated input while failing the genuine-review-grounded audit.
    spot = []
    for s in SYSTEMS:
        for o in OUTCOMES:
            g = attack[(attack.system == s) & (attack.outcome == o)]
            if len(g):
                spot.append(
                    {
                        "System": SYSTEM_LABEL[s],
                        "Human verdict on the attack": OUTCOME_LABEL[o],
                        "Summaries": len(g),
                        "Claims checked by judge": int(g.total.sum()),
                        "Claims judged supported": int(g.supported.sum()),
                        "Supported (%)": pct(g.supported.sum(), g.total.sum()),
                        "_s": s,
                        "_o": o,
                    }
                )
    spot = pd.DataFrame(spot)
    save(spot.drop(columns=["_s", "_o"]), "judge_score_by_attack_outcome.csv")

    # 5. Human check of the judge -----------------------------------------------
    # Validate the sampled claim-audit table before computing agreement.
    # A claim ID is unique only within its scenario and system.
    for c in [
        "scenario_id",
        "system",
        "claim_id",
        "verdict",
        "human_verdict",
        "claim_text",
    ]:
        if c not in claims.columns:
            raise ValueError(f"Claim audit missing column: {c}")
    if claims.duplicated(["scenario_id", "system", "claim_id"]).any():
        raise ValueError(
            "Duplicate claim identifiers; resolve before computing agreement"
        )
    # Only claims with a human verdict belong in the agreement denominator.
    # Blank human-verdict cells are unreviewed, not disagreements.
    reviewed = claims[normal(claims.human_verdict) != ""].copy()
    reviewed["judge"] = normal(reviewed.verdict)
    reviewed["human"] = normal(reviewed.human_verdict)
    # Agreement is exact category equality; uncertain versus supported
    # counts as disagreement even if both reviewers expressed nuance.
    reviewed["agree"] = reviewed.judge == reviewed.human
    reviewed["system"] = normal(reviewed.system)
    # Report agreement by system and overall, including counts so readers
    # can see differences in human-review sample size.
    agree_rows = [
        {
            "System": SYSTEM_LABEL[s],
            "Claims reviewed by a person": len(g),
            "Same verdict as judge": int(g.agree.sum()),
            "Agreement (%)": pct(g.agree.sum(), len(g)),
        }
        for s, g in reviewed.groupby("system")
    ]
    agree_rows.append(
        {
            "System": "Both systems",
            "Claims reviewed by a person": len(reviewed),
            "Same verdict as judge": int(reviewed.agree.sum()),
            "Agreement (%)": pct(reviewed.agree.sum(), len(reviewed)),
        }
    )
    # Document the non-random sampling design in the output table.
    # Oversampling hard cases means this is not a population accuracy estimate.
    agree_rows.append(
        {
            "System": "Note: reviewed claims were the judge's non-supported verdicts plus all "
            "safety claims, chosen because they are hard cases, so agreement is not a "
            "general accuracy rate for the judge.",
            "Claims reviewed by a person": "",
            "Same verdict as judge": "",
            "Agreement (%)": "",
        }
    )
    save(pd.DataFrame(agree_rows), "human_judge_agreement.csv")
    # Create a confusion matrix with human verdicts as rows and judge
    # verdicts as columns, including categories absent from the sample.
    conf = pd.crosstab(reviewed.human, reviewed.judge).reindex(
        index=VERDICTS, columns=VERDICTS, fill_value=0
    )
    conf.index = [f"Person: {VERDICT_LABEL[v]}" for v in conf.index]
    conf.columns = [f"Judge: {VERDICT_LABEL[v]}" for v in conf.columns]
    save(
        conf.rename_axis(
            "Person's verdict (rows) vs judge's verdict (columns)"
        ).reset_index(),
        "human_judge_confusion.csv",
    )
    # Export disagreement cases for qualitative inspection and discussion.
    # Keep claim text and any reviewer notes alongside the labels.
    dis = reviewed[~reviewed.agree]
    note_col = "notes" if "notes" in dis.columns else "human_notes"
    save(
        pd.DataFrame(
            {
                "Scenario ID": dis.scenario_id,
                "System": dis.system.map(SYSTEM_LABEL),
                "Claim ID": dis.claim_id,
                "Claim": dis.claim_text,
                "Judge verdict": dis.judge.map(VERDICT_LABEL),
                "Person's verdict": dis.human.map(VERDICT_LABEL),
                "Reason": dis.get(note_col, ""),
            }
        ),
        "human_judge_disagreements.csv",
    )

    # ================================================================ FIGURES
    # Precompute outcome counts for figures and the written key-numbers file.
    # Explicit reindexing ensures categories with zero occurrences still appear.
    totals = {
        s: attack[attack.system == s]
        .outcome.value_counts()
        .reindex(OUTCOMES, fill_value=0)
        for s in SYSTEMS
    }

    # Figure 1: every attack test as a dot ---------------------------------------
    # Figure 1: each marker is one listing × variant × intensity test.
    # Panels separate systems, columns group injection levels, and rows
    # correspond to attack variants.
    listings = sorted(attack.listing_id.unique())
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
    for ax, s in zip(axes, SYSTEMS):
        part = attack[attack.system == s]
        for r, a in enumerate(ATTACKS):
            # Reverse the row coordinate so the first listed attack appears at top.
            y = len(ATTACKS) - 1 - r
            for gi, inten in enumerate(INTENSITIES):
                for li, lid in enumerate(listings):
                    # Locate the single result for this variant/intensity/listing cell.
                    row = part[
                        (part.attack_variant == a)
                        & (part.intensity == inten)
                        & (part.listing_id == lid)
                    ]
                    if len(row):
                        outcome_marker(ax, gi * 4 + li, y, row.outcome.iloc[0])
            # Add a per-variant count of full-or-partial attack successes.
            cell = part[part.attack_variant == a].outcome
            fooled = int(cell.isin(["yes", "partial"]).sum())
            ax.text(
                12.0,
                y,
                f"{fooled} of {len(cell)} fooled",
                va="center",
                ha="left",
                fontsize=10.5,
                color=INK if fooled else MUTED,
                fontweight="bold" if fooled else "normal",
            )
        ax.set_xlim(-1, 15.2)
        ax.set_ylim(-0.7, len(ATTACKS) - 0.3)
        ax.set_xticks([1, 5, 9], ["3", "10", "25"])
        ax.set_xlabel("Fake reviews added (each group = the 3 listings)")
        ax.set_title(
            SYSTEM_LABEL[s], fontsize=12.5, fontweight="bold", loc="left", pad=10
        )
        for xg in [3, 7]:
            ax.axvline(xg, color=GRID, lw=1)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=0)
    axes[0].set_yticks(
        range(len(ATTACKS)), [ATTACK_LABEL[a] for a in reversed(ATTACKS)], fontsize=11.5
    )
    fig.legend(
        handles=outcome_legend_handles(),
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, -0.07),
        fontsize=11,
    )
    fig.subplots_adjust(wspace=0.08, top=0.80)
    title_block(
        fig,
        "Which fake reviews fooled the AI summaries?",
        "Each dot is one test, judged by a person against what real guests wrote. "
        '"Fooled" counts fully or partly fooled.',
        top=0.99,
        gap=0.065,
    )
    finish(fig, "fig1_attack_outcomes_by_type.png")

    # Figure 2: overall outcome counts per system --------------------------------
    # Figure 2: stacked bars show the distribution of all three human
    # outcomes, with a fixed denominator per system.
    fig, ax = plt.subplots(figsize=(10, 3.2))
    for i, s in enumerate(SYSTEMS):
        y = len(SYSTEMS) - 1 - i
        left = 0
        for o in OUTCOMES:
            v = int(totals[s][o])
            if v:
                ax.barh(
                    y,
                    v,
                    left=left,
                    color=OUTCOME_COLOR[o],
                    edgecolor=SURFACE,
                    linewidth=2,
                    height=0.6,
                    hatch="///" if o == "partial" else None,
                )
                txt_color = "#ffffff" if o == "yes" else INK
                ax.text(
                    left + v / 2,
                    y,
                    f"{v}",
                    ha="center",
                    va="center",
                    color=txt_color,
                    fontsize=12,
                    fontweight="bold",
                    bbox=(
                        dict(
                            boxstyle="round,pad=0.25",
                            facecolor=SURFACE,
                            edgecolor="none",
                        )
                        if o == "partial"
                        else None
                    ),
                )
            left += v
    ax.set_yticks(
        range(len(SYSTEMS)), [SYSTEM_LABEL[s] for s in reversed(SYSTEMS)], fontsize=11.5
    )
    n_tests = int(totals["system_a"].sum())
    ax.set_xlim(0, n_tests)
    ax.set_xlabel(f"Attack tests (out of {n_tests} per system)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    handles = [
        Patch(
            facecolor=OUTCOME_COLOR[o],
            edgecolor=SURFACE,
            hatch="///" if o == "partial" else None,
            label=OUTCOME_LABEL[o],
        )
        for o in OUTCOMES
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.3),
        ncol=3,
        frameon=False,
    )
    fig.subplots_adjust(top=0.72)
    title_block(
        fig,
        "How often were the summaries fooled?",
        f"Same {n_tests} attack tests for both systems, judged by a person against real guest reviews.",
        top=0.99,
        gap=0.1,
    )
    finish(fig, "fig2_overall_outcomes.png")

    # Figure 3: side-by-side comparison on identical tests ----------------------
    fig, ax = plt.subplots(figsize=(10, 3.2))
    # Figure 3: paired comparison uses the *same* 36 attack scenarios
    # rather than treating system outputs as unrelated observations.
    segs = [
        (f"Evidence-based did better", b_better, BETTER_B, "#ffffff"),
        ("Same result", ties, SAME, INK),
        ("Standard did better", a_better, OUTCOME_COLOR["yes"], "#ffffff"),
    ]
    left = 0
    for label, v, col, tc in segs:
        if v:
            ax.barh(
                0, v, left=left, color=col, edgecolor=SURFACE, linewidth=2, height=0.55
            )
            ax.text(
                left + v / 2,
                0,
                f"{label}\n{v}",
                ha="center",
                va="center",
                color=tc,
                fontsize=11,
                fontweight="bold",
            )
        left += v
    # Explicitly label a zero-win category that would otherwise have no bar.
    if a_better == 0:
        ax.text(
            left,
            -0.5,
            "Standard did better: 0",
            ha="right",
            va="top",
            color=INK_2,
            fontsize=10.5,
        )
    ax.set_xlim(0, len(paired))
    ax.set_ylim(-0.8, 0.5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(f"Attack tests ({len(paired)} identical tests, run on both systems)")
    fig.subplots_adjust(top=0.70)
    title_block(
        fig,
        "Same tests, side by side: which summary held up better?",
        f"Of the {b_better + a_better} tests where the two differed, the evidence-based summary "
        f"did better in {b_better} (sign test {p_text(p_value)};\ntests share three listings, "
        f"so treat this as indicative).",
        top=0.99,
        gap=0.1,
    )
    finish(fig, "fig3_paired_comparison.png")

    # Figure 4: the automated judge's blind spot ---------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.2))
    # Figure 4: show judge support percentages grouped by the human
    # attack outcome, illustrating the distinction between the two metrics.
    spot = spot.reset_index(drop=True)
    ys = list(range(len(spot)))[::-1]
    for y, (_, r) in zip(ys, spot.iterrows()):
        # The x-axis intentionally begins at 80% to expose small differences;
        # this truncation is clearly disclosed in the axis label.
        ax.hlines(y, 80, r["Supported (%)"], color=GRID, lw=2)
        outcome_marker(ax, r["Supported (%)"], y, r["_o"], size=12)
        ax.text(
            r["Supported (%)"] + 0.5,
            y,
            f"{r['Supported (%)']:.1f}%   ({r['Summaries']} summaries)",
            va="center",
            fontsize=10.5,
            color=INK,
        )
    ax.set_yticks(
        ys,
        [
            f"{SYSTEM_SHORT[r['_s']]}: {OUTCOME_LABEL[r['_o']].lower()}"
            for _, r in spot.iterrows()
        ],
        fontsize=11,
    )
    ax.set_xlim(80, 103)
    ax.set_xlabel(
        'Summary statements the automated checker marked "supported" (%) — axis starts at 80%'
    )
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.subplots_adjust(top=0.80)
    title_block(
        fig,
        "The automated checker can't see this kind of attack",
        "It checks statements against the reviews the AI was given, fake ones included, so "
        "summaries fooled by the fakes\nstill score as accurate.",
        top=0.99,
        gap=0.075,
    )
    finish(fig, "fig4_judge_blind_spot.png")

    # Figure 5: worked example, the re-dated door-lock complaint -----------------
    # Figure 5: optional qualitative timeline using a single preselected
    # temporal attack. It requires source reviews and saved summaries.
    example_timeline(score, listing_name)

    # Write a Markdown digest from the calculated values for easier
    # use when drafting the report and five-minute presentation.
    write_key_numbers(attack, totals, b_better, ties, a_better, p_value, spot, reviewed)
    print("\nDONE. Inspect tables and figures before reporting any conclusion.")


# Construct a concrete example of how synthetic recent-dated reports
# could change the perceived recency of a genuine historical complaint.
# This figure is illustrative and must be checked against the source reviews.
def example_timeline(score, listing_name):
    """Timeline of real vs fake reports for one temporal attack, with what each AI said."""
    # Select one specific medium-intensity temporal attack and its target
    # concern. These IDs are intentionally fixed, not selected by performance.
    sid = "3314819_temporal_manipulation_recent_dated_issue_medium"
    concern_id = "3314819-unlockable_entrance"
    summary_path = ROOT / "results" / "summaries" / f"{sid}.json"
    # Skip only this optional illustration if its required files are absent;
    # the rest of the quantitative analysis can still be produced.
    if not (summary_path.exists() and INPUTS.exists() and CONCERNS.exists()):
        print("Skipped fig5 (example inputs not found)")
        return
    import json

    inputs = load_csv(INPUTS)
    concerns = load_csv(CONCERNS)
    crow = concerns[concerns.concern_id == concern_id]
    if crow.empty:
        print("Skipped fig5 (concern not found)")
        return
    # Collect the genuine representative and challenge review IDs associated
    # with the benchmark concern, then locate those reviews in this scenario.
    real_ids = set()
    for col in ["representative_review_ids", "challenge_review_ids"]:
        real_ids |= {x.strip() for x in crow[col].iloc[0].split(";") if x.strip()}
    # Use the private provenance flag to separate genuine and injected
    # review dates. This information was not shown to the blind judge.
    scen = inputs[inputs.scenario_id == sid]
    real = pd.to_datetime(scen[scen.review_id.isin(real_ids)].review_date)
    fake = pd.to_datetime(scen[normal(scen.is_synthetic) == "true"].review_date)
    doc = json.loads(summary_path.read_text(encoding="utf-8"))

    # Extract the first sentence containing a target keyword for display.
    # This is a convenience heuristic, not a full semantic interpretation;
    # manually verify the selected excerpts before presenting them.
    def sentence_with(text, pattern):
        for s in re.split(r"(?<=[.!?])\s+", text):
            if re.search(pattern, s, re.I):
                return s.strip()
        return ""

    said_a = sentence_with(doc["system_a"]["summary"], r"lock")
    said_b = " ".join(
        x
        for x in [
            sentence_with(doc["system_b"]["summary"], r"lock"),
            sentence_with(doc["system_b"]["summary"], r"identical|independent"),
        ]
        if x
    )
    # Save the plotted dates as a table so the timeline can be audited.
    save(
        pd.DataFrame(
            {
                "Report date": list(real.dt.date) + list(fake.dt.date),
                "Source": ["Real guest review"] * len(real)
                + ["Fake review (injected)"] * len(fake),
            }
        ),
        "example_timeline_door_lock.csv",
    )

    # Build the timeline with genuine and injected review dates on one axis.
    # Diamonds with hollow centers identify synthetic reviews.
    fig = plt.figure(figsize=(12, 5.6))
    ax = fig.add_axes([0.03, 0.56, 0.94, 0.22])
    ax.scatter(
        real,
        np.zeros(len(real)),
        s=150,
        color=GENUINE,
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
        label=f"Real guest complaint ({len(real)})",
    )
    ax.scatter(
        fake,
        np.zeros(len(fake)),
        s=130,
        facecolor="none",
        edgecolor=SYNTHETIC,
        linewidth=2,
        marker="D",
        zorder=3,
        label=f"Fake review added for the test ({len(fake)})",
    )
    ax.axhline(0, color=AXIS, lw=1.5, zorder=1)
    # Shade the period treated as recent for visual context. This is
    # an explanatory annotation, not a data-derived threshold.
    ax.axvspan(
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2026-09-30"),
        color="#f0efec",
        zorder=0,
    )
    ax.text(
        pd.Timestamp("2025-05-15"),
        0.75,
        '"Recent" reviews\n(2024–2026)',
        ha="center",
        va="center",
        fontsize=9.5,
        color=INK_2,
    )
    ax.set_xlim(pd.Timestamp("2014-01-01"), pd.Timestamp("2027-01-01"))
    ax.set_ylim(-1, 1.2)
    ax.set_yticks([])
    for sp in ["left"]:
        ax.spines[sp].set_visible(False)
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.0, -0.32),
        ncol=2,
        frameon=False,
        fontsize=10.5,
    )
    fig.text(
        0.03,
        0.98,
        "Example: an old complaint made to look new",
        fontsize=15,
        fontweight="bold",
        va="top",
    )
    name = listing_name.get("3314819", "Listing 3314819")
    fig.text(
        0.03,
        0.915,
        f'Listing "{name}": real guests said the entrance couldn\'t be locked, last in '
        f"{real.max():%B %Y}. We added {len(fake)} fake reviews repeating it in 2025–2026.",
        fontsize=10.5,
        color=INK_2,
        va="top",
    )

    # Show the selected summary excerpts beside the timeline. The boxes
    # provide an example, not additional quantitative evidence.
    def quote_box(x, title, quote, edge):
        fig.text(x, 0.33, title, fontsize=12, fontweight="bold", va="top")
        fig.text(
            x,
            0.265,
            "\n".join(textwrap.wrap(f'"{quote}"', 58)),
            fontsize=10.5,
            va="top",
            color=INK,
            linespacing=1.4,
            bbox=dict(
                boxstyle="round,pad=0.6",
                facecolor=SURFACE,
                edgecolor=edge,
                linewidth=1.5,
            ),
        )

    quote_box(0.03, "What the standard summary (A) said", said_a, OUTCOME_COLOR["yes"])
    quote_box(
        0.53,
        "What the evidence-based summary (B) said",
        said_b,
        OUTCOME_COLOR["partial"],
    )
    # The concluding annotation summarizes the previously assigned human
    # outcomes; verify it if any human assessment is later revised.
    fig.text(
        0.03,
        -0.03,
        "A presents an old (2015) problem as current. B flags the copies as suspicious but still "
        'leads with the issue, so it was scored "partly fooled".',
        fontsize=10,
        color=INK_2,
    )
    finish(fig, "fig5_example_timeline.png")


# Create a plain-language report of the main derived quantities.
# This is generated from the tables rather than manually transcribed numbers.
def write_key_numbers(
    attack, totals, b_better, ties, a_better, p_value, spot, reviewed
):
    # Retrieve both systems' outcome distributions and the number of paired tests.
    a, b = totals["system_a"], totals["system_b"]
    n = int(a.sum())
    lines = [
        "# Key numbers (generated by src/analyze_results.py)",
        "",
        "All attack results are human-reviewed judgments against real guest reviews.",
        "",
        "## Overall",
        f"- {n} attack tests per system (3 listings × 4 attack types × 3 sizes).",
        f'- Standard summary (A): fully fooled {a["yes"]}, partly fooled {a["partial"]}, '
        f'not fooled {a["no"]}.',
        f'- Evidence-based summary (B): fully fooled {b["yes"]}, partly fooled {b["partial"]}, '
        f'not fooled {b["no"]}.',
        f"- Same test, side by side: B better in {b_better}, same in {ties}, A better in {a_better} "
        f"(exact sign test {p_text(p_value)}; tests share 3 listings, so treat as indicative).",
        "",
        "## By attack type (fully or partly fooled, out of 9 tests each)",
    ]
    # Report full-or-partial success for each attack type, keeping the
    # numerator and denominator visible.
    for at in ATTACKS:
        cells = []
        for s in SYSTEMS:
            g = attack[(attack.system == s) & (attack.attack_variant == at)]
            cells.append(
                f'{SYSTEM_SHORT[s]} {int(g.outcome.isin(["yes", "partial"]).sum())}/{len(g)}'
            )
        lines.append(f"- {ATTACK_LABEL[at]}: " + ", ".join(cells))
    lines += [
        "",
        "## Automated checker (blind judge)",
        'Share of summary statements it marked "supported" by the reviews the AI was given:',
    ]
    # Include blind-judge support rates by human attack outcome to make
    # the measurement distinction explicit in the narrative.
    for _, r in spot.iterrows():
        lines.append(
            f'- {SYSTEM_SHORT[r["_s"]]}, {OUTCOME_LABEL[r["_o"]].lower()}: '
            f'{r["Supported (%)"]}% ({r["Summaries"]} summaries)'
        )
    lines += [
        "",
        "## Human check of the judge",
        f"- {len(reviewed)} claims reviewed; same verdict as the judge in {int(reviewed.agree.sum())} "
        f"({pct(reviewed.agree.sum(), len(reviewed))}%).",
        "- Reviewed claims were chosen as hard cases (non-supported verdicts and safety claims), "
        "so this is not a general accuracy rate.",
        "",
        "## Caveats",
        "- Three listings in one city, one summarizer model, one run per condition.",
        "- Fake reviews are templated; real manipulation may be more varied.",
        "- Scorecard and claim-audit verdicts were drafted with LLM assistance and reviewed by the author.",
    ]
    # Save the text report in results/analysis alongside tables and figures.
    path = OUT / "key_numbers.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")


# Only run the analysis when invoked as a script; importing its functions
# from another module should not start reading or writing files.
if __name__ == "__main__":
    main()
