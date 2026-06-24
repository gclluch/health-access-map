# Multiplicative gap lens - need-AND-barrier coincidence

**Status: SHIPPED 2026-06-23 as a selectable lens (`access_gap_mult_pctile`), NOT the default.**
Implements COMPOSITE-ENHANCEMENT.md rec 6. Build: `pipeline/join_and_score.py`.

## The construct problem it fixes

The default `access_gap_score` is a weighted **arithmetic** mean of the 3 dimension percentiles -
**fully compensatory**: a surplus in one dimension fully offsets a deficit in another. So it
scores "high need, fine access" (need 90 / barrier 10) the **same** as "low need, terrible
access" (need 10 / barrier 90) - both land mid-scale. For a *targeting* tool that is a category
error: the access gap should light up where need **and** barriers **coincide**.

## The fix (principled, not a hack)

The OECD/JRC Handbook's standard alternative to linear aggregation is **geometric aggregation**
(partial compensability). `access_gap_mult` = the weighted **geometric** mean of the same three
dimension percentiles with the same weights (frac clipped to [0.01, 1] so a 0-rank dimension
can't zero the product; renormalized over present dims). A deficit in one dimension can no longer
be fully bought back by a surplus in another, so the score concentrates on coincidence.

## Gate (all pass; the additive default is untouched)

| Gate | Additive (default) | Geometric (lens) | Verdict |
|---|---|---|---|
| outcome mean-r, all 6 | +0.495 | +0.491 | ~identical |
| outcome mean-r, clean (death/ACSC) | +0.502 | +0.500 | ~identical - does NOT collapse |
| rank corr (add vs geo) | - | **+0.994** | same gradient |
| coverage (scoreable) | 33176 | 33176 | identical |
| NY sub-county within-O/E | +0.482 | +0.473 | expected compensability tradeoff |

**Construct validity (the point):** at the tails the two diverge as intended -

| ZCTA group | n | additive median pctile | geometric median pctile | Δ |
|---|---|---|---|---|
| need AND barrier both >=80 (coincidence) | 2841 | 95.1 | 95.2 | **+0.1** (preserved) |
| need-only (need>=80, barrier<=40) | 655 | 62.9 | 58.6 | **−4.2** (down-weighted) |
| barrier-only (need<=40, barrier>=80) | 695 | 57.0 | 52.5 | **−4.5** (down-weighted) |

The lens preserves coincidence-highs and pulls down one-dimensional highs by ~4-5 percentile pts -
exactly the targeting property. Because it tracks outcomes ~identically, this is a **construct**
choice (how to define the gap), not a signal change - so it is gated on construct validity +
no-outcome-regression, **not** on an outcome-r lift (gating it on outcome-r would wrongly reject a
correct construct, since the additive form is the one that maximizes outcome correlation).

## How it ships

- Stored: `access_gap_mult` + `access_gap_mult_pctile` in `metrics.parquet`; the pctile is in the
  slim `metrics.json` frontend payload.
- **Default stays additive.** The geometric form is a one-click *lens*, matching the slider
  philosophy (the user owns the compensability assumption, just as they own the weights).
- **Remaining (frontend):** add a lens toggle (additive ↔ multiplicative) that colors the map by
  `access_gap_mult_pctile`. The data is already in the payload; only the UI control is left.
