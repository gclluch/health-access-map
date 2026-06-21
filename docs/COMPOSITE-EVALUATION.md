# Composite Evaluation - is the Access Gap meaningful, and does it compare ZIPs?

Rigorous evaluation (2026-06-21) against the OECD/JRC composite-indicator framework, using
statistics on the live national build (33,181 scoreable ZCTAs) + the small-area-uncertainty
literature (`docs/uncertainty-research.md`). Reproducible from `/tmp/evaluate.py` + `/tmp/eval2.py`.

## Verdict

**Meaningful and informative: yes.** **Fine-grained ZIP-to-ZIP comparison: no - only coarse
tiers.** The composite is a reliable, externally-valid *general access-disadvantage gradient*,
but its resolution is ~7-10 tiers, not 33k distinct ranks. The honest, salient presentation is
deciles + uncertainty, not an integer leaderboard.

## The numbers

| Test (OECD/JRC dimension) | Result | Reading |
|---|---|---|
| **Internal reliability** (split-half, Spearman-Brown) | **0.94** (low-pop 0.93, high-pop 0.97) | Strong. The ~50 measures cohere; as a measurement instrument it's reliable. |
| **External validity** (vs independent outcomes) | r = +0.52 LE, +0.49 premature death, +0.40 infant mort., +0.23 ACSC | Moderate, correctly signed. Comparable to SDI's published validation. It tracks real outcomes. |
| **Weighting robustness - plausible weights** (each dim 15-55%) | median rank interval **12 pts** | A ZIP's rank wobbles ~±6 pts under defensible weight choices. |
| **Weighting robustness - full simplex** | median rank interval 28 pts; default vs equal Spearman 0.999 | Extreme weightings move ranks a lot; *reasonable* weightings barely do (0.999). |
| **Internal measurement noise** (split-half SE) | SE ≈ 2.6 score pts; 95% min detectable gap ≈ **7 pts** | Two ZIPs <7 pts apart are within measurement noise. |
| **Dimensionality** | PC1 of 11 sub-scores = 46% (7 PCs for 90%); **corr(composite, PC1) = 0.94** | Multi-dimensional underneath, but the composite is ~94% a single "general deprivation" gradient - like ADI/SVI. |

**Combined comparability threshold:** measurement noise (~7) + plausible-weight sensitivity
(~12) ⇒ **two ZIPs are reliably different only if they differ by ~10-15 percentile points.**
That implies **~7-10 reliably-distinct tiers**, not 33,181 ranks.

## What the literature says (so this isn't just our number)

- **ACS small-area error** is large and *spatially structured* (tract MOEs ~75% larger than the
  long form; for some counts MOE > estimate in >72% of tracts), concentrated in exactly the
  poor/urban ZCTAs the gap cares about - so it does **not** cancel in a composite (Spielman/Folch/Nagle).
- **ADI** explicitly forbids ZIP/ZCTA use ("not validated"; imprecise "where concentrated poverty
  abuts wealthy regions"). **SVI / CHR / ADI all publish ranks with no rank-level confidence
  interval** - the literature (Saisana/Saltelli/Tarantola; OECD/JRC) calls that a deficiency.
- A dominant PC1 is a *feature, not a defect* (it's one coherent gradient) - but it must be
  reported honestly, not marketed as three independent dimensions.

## Therefore - how to make it salient (ranked by leverage)

1. **Rank confidence intervals + a "can't tell these apart" rule.** Show each ZIP as a median
   rank + 5-95 interval (Monte-Carlo over weights, later also over input noise). When two ZIPs'
   intervals overlap, say so. **No production index (ADI/SVI/CHR) does this** - it's the single
   biggest honesty-and-differentiation win.
2. **Bin to coarse tiers** (deciles or a 7-tier scale) + part-to-whole language ("worse access
   than 85% of U.S. ZIPs"), instead of implying integer-rank precision the data can't support.
3. **Cut the input noise (shrinkage).** 31% of scoreable ZCTAs are low-confidence; empirical-Bayes
   shrinkage of ACS inputs (using their MOEs) tightens the intervals where it matters most.
4. **Make reliability visible.** `low_confidence` already exists; surface it as per-ZCTA shading
   + explanation rather than only excluding it from rankings.
5. **State the dimensionality honestly** in-product (PC1 ≈ general gradient; the 3 dimensions are
   a decomposition, ~0.5 correlated).

## Bottom line for the product

Keep the composite - it's reliable and valid as a *gradient*. Stop implying it resolves 33k
distinct ranks. Lead with tiers + uncertainty, and ship the rank-CI machinery the federal indices
omit. That converts a defensible-but-overprecise score into an honest, differentiated instrument.
