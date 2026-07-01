"""validate_fqhc_power: the go/no-go POWER ANALYSIS for the staggered FQHC event study (BACKLOG
B5d.0) - run this BEFORE assembling any HRSA New Access Point treatment panel.

The proposed study (B5d): HRSA awards New Access Point (NAP) grants in waves, each opening a dated,
located FQHC - a staggered shock to the SUPPLY / safety-net arm of `care_access` (the arm the ACA
work in §7b/§7e never touched). With many adoption years the estimator would be Callaway & Sant'Anna
(2021) group-time ATT. The fatal risk is NOT identification - it is POWER: one new clinic captures
only a fraction of a ZIP's residents, so the ZIP-level ACSC effect is small, fighting noisy,
serially-correlated ZIP rates. A null could then mean "no effect" OR "couldn't have seen one" - far
weaker than §7e's falsification. This module decides which world we are in, for ~no new data.

Method (Monte Carlo):
  1. NOISE FLOOR, from real data, DECOMPOSED. Take the actual NY SPARCS ACSC panel (reuse
     validate_temporal), two-way (ZIP+year) demean it, and regress each ZIP's residual variance on
     1/population. This splits the noise into an IRREDUCIBLE heterogeneity floor (a) plus a SAMPLING
     term (b/pop) that shrinks in big ZIPs. Also measures within-ZIP AR(1) (rho) + the baseline
     level. Precision-weighting (lever 3, VALIDATION §7d) can only beat the sampling term, never the
     floor - which is exactly why the decomposition matters.
  2. SIMULATE a balanced staggered-adoption panel with HETEROSKEDASTIC ZIPs (each ZIP's noise
     sigma_z = sqrt(a + b/pop_z), pops drawn from the real distribution): n_treated adopt a NAP in
     assorted years, n_control never do; inject a KNOWN homogeneous effect tau; add AR(1) noise.
  3. ESTIMATE tau with a two-way-FE DiD under EQUAL vs POPULATION weighting (WLS), ZIP-cluster-robust
     SE (the project's standard inference); reject at 5% two-sided. Power = rejection rate.
  4. MDE = smallest |tau| with power >= 0.80, per weighting. Compare to the plausible FQHC band.

Decision rule (printed): MDE (under the better weighting) vs the plausible band floor/ceiling.
Read-only; never feeds the composite.

    python -m pipeline.validate_fqhc_power
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .common import log

# Plausible ZIP-level ACSC reduction from ONE new FQHC, as a fraction of the baseline rate.
# (catchment penetration ~5-20% of residents) x (per-user ACSC reduction ~10-40%) -> ~1-8% at the
# ZIP aggregate. Anchored loosely to the community-health-center literature (Bailey & Goodman-Bacon
# 2015 on CHC mortality; CHC->ACSC-hospitalization studies). The ASSUMPTION the verdict is judged
# against; widening it only sharpens the conclusion. Stated, not hidden.
PLAUSIBLE_FRAC = (0.02, 0.08)

# Treated-N is now GROUNDED in real HRSA data, not guessed. Counting "Site Added to Scope" openings
# (active, geocoded, 2012-2019) assigned to ZCTAs across the four outcome-panel states (NY/TX/CO/CA):
# 1,685 openings -> 874 unique ZCTAs touched -> 555 NEWLY-served ZCTAs (no prior site = the clean
# "new access point" treatment), in 8 staggered cohorts of 51-100/yr. Scenarios discount 555 for
# ZCTAs that won't have clean ACSC outcome coverage + a usable pre-period; controls = the rest of the
# four state panels (~3k ZCTAs). The earlier 40-150 guesses were an order of magnitude too low.
SCENARIOS = [
    # label,         n_treated, n_control, n_years
    ("all4-states",  555,       2500,      10),   # all 4 states' clean openings, IF all had panels
    ("NY+TX (real)", 277,       2600,      10),   # the ACTUALLY-buildable event-study N: NY 135 + TX
                                                  # 142 newly-served ZCTAs. CO (35) and CA (243) are
                                                  # POOLED cross-sections (no annual ACSC panel), so
                                                  # they can't join a staggered event study.
    ("NY-only",      135,       1200,      12),   # Phase-1 pilot (data fully in hand, no TX download)
]

N_REP = 400
ALPHA = 1.96
TARGET_POWER = 0.80
SEED = 20260626
DEMEAN_ITERS = 6


class Noise(NamedTuple):
    a: float            # irreducible heterogeneity variance (the floor WLS can't beat)
    b: float            # sampling coefficient: per-ZIP var ~= a + b/pop
    rho: float          # within-ZIP AR(1) of the residual
    level: float        # baseline ACSC rate /100k (converts fractional effects to absolute)
    pops: np.ndarray    # empirical population distribution of panel ZIPs
    source: str

    @property
    def sigma_equal(self) -> float:
        return float(np.sqrt(self.a + self.b * np.mean(1.0 / self.pops)))

    @property
    def sigma_popw(self) -> float:
        # effective floor when big ZIPs dominate: mean(1/pop) -> 1/mean(pop)
        return float(np.sqrt(self.a + self.b / np.mean(self.pops)))


def estimate_noise() -> Noise:
    """Decompose the REAL NY ACSC residual variance into (a) a heterogeneity floor and (b) a
    sampling term b/pop, plus AR(1) and level. Falls back to a flagged literature default if the
    Socrata fetch is unavailable."""
    try:
        import pandas as pd

        from . import config
        from .validate_temporal import _build_panel, _twoway_demean
        j, _years = _build_panel()
        m = pd.read_parquet(config.PROCESSED / "metrics.parquet")[["zcta5", "population"]]
        m["zcta5"] = m["zcta5"].astype(str)
        j = j.merge(m, on="zcta5", how="left")
        level = float(j["rate"].mean())
        dm = _twoway_demean(j, ["rate"])
        dm["zcta5"], dm["population"] = j["zcta5"], j["population"]

        # per-ZIP residual variance and population, then var_z ~ a + b*(1/pop)
        g = dm.groupby("zcta5")
        var_z = g["rate"].var()
        pop_z = g["population"].first().reindex(var_z.index)
        ok = var_z.notna() & pop_z.notna() & (pop_z > 0)
        x = (1.0 / pop_z[ok]).to_numpy()
        y = var_z[ok].to_numpy()
        b, a = np.polyfit(x, y, 1)            # slope=sampling, intercept=floor
        a, b = max(float(a), 1.0), max(float(b), 0.0)

        # within-ZIP lag-1 autocorrelation of the demeaned residual, averaged over ZIPs
        rhos = []
        for _z, gg in dm.sort_values("year").groupby("zcta5"):
            r = gg["rate"].to_numpy()
            if len(r) >= 4 and r[:-1].std() > 0 and r[1:].std() > 0:
                rhos.append(np.corrcoef(r[:-1], r[1:])[0, 1])
        rho = float(np.clip(np.nanmean(rhos), 0.0, 0.95)) if rhos else 0.3
        pops = pop_z[ok].to_numpy().astype(float)
        log("fqhc-power", f"noise from REAL NY panel: {len(pops)} ZIPs, "
                          f"floor sqrt(a)={np.sqrt(a):.0f}, sampling b={b:.2e}")
        return Noise(a, b, rho, level, pops, "REAL NY SPARCS panel")
    except Exception as e:  # noqa: BLE001 - network/data unavailable; flagged fallback
        log("fqhc-power", f"real-panel fetch failed ({type(e).__name__}); literature fallback")
        pops = np.array([1500, 3000, 6000, 12000, 25000, 50000], dtype=float)
        return Noise(a=60_000.0, b=4.0e8, rho=0.35, level=1500.0, pops=pops, source="LITERATURE fallback")


def _ar1_noise(sigma_z: np.ndarray, n_year: int, rho: float, rng: np.random.Generator) -> np.ndarray:
    """(n_zip x n_year) AR(1) residuals with per-ZIP marginal SD sigma_z and lag-1 corr rho."""
    n = len(sigma_z)
    e = np.empty((n, n_year))
    e[:, 0] = rng.normal(0, 1, n) * sigma_z
    k = np.sqrt(1.0 - rho * rho)
    for t in range(1, n_year):
        e[:, t] = rho * e[:, t - 1] + rng.normal(0, 1, n) * sigma_z * k
    return e


def _wdemean(M: np.ndarray, w: np.ndarray, n_iter: int = DEMEAN_ITERS) -> np.ndarray:
    """Two-way (row=ZIP, col=year) within transform under ZIP-level weights w (constant within a
    ZIP, so the row mean is unweighted and only the YEAR mean is weighted). Alternating projections."""
    out = M.astype(float).copy()
    ws = w.sum()
    for _ in range(n_iter):
        out = out - out.mean(axis=1, keepdims=True)                 # ZIP (row) demean
        colw = (w[:, None] * out).sum(axis=0) / ws                  # weighted year (col) mean
        out = out - colw[None, :]
    return out


def simulate_power(n_t: int, n_c: int, n_year: int, tau_frac: float, noise: Noise,
                   weighting: str, rng: np.random.Generator, n_rep: int = N_REP) -> float:
    """Rejection rate of a two-way-FE DiD (EQUAL or POP weighting), ZIP-cluster-robust SE, when the
    true effect is a tau_frac reduction of the baseline rate. Heteroskedastic ZIPs: sigma_z scales
    with 1/pop, pops drawn from the real distribution. Treated ZIPs adopt in spread interior years."""
    n_zip = n_t + n_c
    tau = tau_frac * noise.level
    pops = rng.choice(noise.pops, size=n_zip)
    sigma_z = np.sqrt(np.clip(noise.a + noise.b / pops, 1.0, None))
    w = pops.copy() if weighting == "pop" else np.ones(n_zip)
    G = n_zip
    cr1 = G / (G - 1.0)

    adopt = rng.integers(1, n_year, size=n_t)
    D = np.zeros((n_zip, n_year))
    yr = np.arange(n_year)
    for i in range(n_t):
        D[i, yr >= adopt[i]] = 1.0
    d_dm = _wdemean(D, w)
    den = float((w[:, None] * d_dm * d_dm).sum())
    if den <= 0:
        return float("nan")

    rejects = 0
    for _ in range(n_rep):
        E = _ar1_noise(sigma_z, n_year, noise.rho, rng)
        Y = -tau * D + E
        y_dm = _wdemean(Y, w)
        beta = float((w[:, None] * d_dm * y_dm).sum() / den)
        resid = y_dm - beta * d_dm
        s_z = w * (d_dm * resid).sum(axis=1)        # per-ZIP cluster score (weight constant in ZIP)
        se = np.sqrt(cr1 * float((s_z * s_z).sum())) / den
        if se > 0 and abs(beta / se) > ALPHA:
            rejects += 1
    return rejects / n_rep


GRID = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.20]


def mde(n_t: int, n_c: int, n_year: int, noise: Noise, weighting: str,
        rng: np.random.Generator) -> tuple[float, list[tuple[float, float]]]:
    curve = [(f, simulate_power(n_t, n_c, n_year, f, noise, weighting, rng)) for f in GRID]
    hit = [f for f, p in curve if p >= TARGET_POWER]
    return (min(hit) if hit else float("nan")), curve


def run() -> dict:
    noise = estimate_noise()
    rng = np.random.default_rng(SEED)
    se, sp = noise.sigma_equal, noise.sigma_popw
    print("\n=== FQHC staggered event study - POWER ANALYSIS (B5d.0 go/no-go gate) ===")
    print(f"  noise ({noise.source}): heterogeneity FLOOR sqrt(a) = {np.sqrt(noise.a):.0f}/100k "
          f"(WLS can't beat this), AR(1) rho = {noise.rho:.2f}, baseline = {noise.level:.0f}/100k")
    print(f"  effective residual SD: equal-weight {se:.0f}/100k  ->  pop-weight {sp:.0f}/100k "
          f"({(1 - sp / se) * 100:.0f}% lower - lever 3)")
    print(f"  plausible FQHC effect band: {PLAUSIBLE_FRAC[0]*100:.0f}-{PLAUSIBLE_FRAC[1]*100:.0f}% "
          f"= {PLAUSIBLE_FRAC[0]*noise.level:.0f}-{PLAUSIBLE_FRAC[1]*noise.level:.0f}/100k")
    print(f"  test: 2-way-FE DiD, ZIP-cluster SE, two-sided 5%, target power {TARGET_POWER:.0%}, "
          f"{N_REP} reps\n")

    rep: dict = {"source": noise.source, "floor_sd": round(float(np.sqrt(noise.a)), 1),
                 "rho": round(noise.rho, 3), "level": round(noise.level, 1),
                 "sigma_equal": round(se, 1), "sigma_popw": round(sp, 1),
                 "plausible_frac": list(PLAUSIBLE_FRAC), "scenarios": {}}

    print(f"  {'scenario':13s} {'treated':>7s} {'yrs':>4s}   "
          f"{'MDE equal':>10s} {'MDE pop-w':>10s}   verdict (pop-weighted)")
    curves = {}
    for label, n_t, n_c, n_y in SCENARIOS:
        m_eq, _ = mde(n_t, n_c, n_y, noise, "equal", rng)
        m_pw, curve_pw = mde(n_t, n_c, n_y, noise, "pop", rng)
        curves[label] = curve_pw
        mid = float(np.mean(PLAUSIBLE_FRAC))
        verdict = ("DETECTS even the floor effect" if (not np.isnan(m_pw)) and m_pw <= PLAUSIBLE_FRAC[0]
                   else "detects the LIKELY effect" if (not np.isnan(m_pw)) and m_pw <= mid
                   else "upper band only" if (not np.isnan(m_pw)) and m_pw <= PLAUSIBLE_FRAC[1]
                   else "UNDERPOWERED vs plausible band")
        rep["scenarios"][label] = {
            "n_treated": n_t, "n_control": n_c, "n_years": n_y,
            "mde_equal": None if np.isnan(m_eq) else round(m_eq, 3),
            "mde_popw": None if np.isnan(m_pw) else round(m_pw, 3),
            "mde_popw_per100k": None if np.isnan(m_pw) else round(m_pw * noise.level, 1),
            "power_curve_popw": {f"{f:.2f}": round(p, 2) for f, p in curve_pw},
            "verdict": verdict,
        }
        et = "  none" if np.isnan(m_eq) else f"{m_eq*100:8.0f}%"
        pt = "  none" if np.isnan(m_pw) else f"{m_pw*100:8.0f}%"
        print(f"  {label:13s} {n_t:>7d} {n_y:>4d}   {et:>10s} {pt:>10s}   {verdict}")

    KEY = "NY+TX (real)"   # the actually-buildable event-study design; decision is read off this
    print(f"\n  '{KEY}' power curve, POP-WEIGHTED (effect as % of baseline ACSC):")
    for f, p in curves[KEY]:
        bar = "#" * int(round(p * 30))
        mark = "  <- target" if abs(p - TARGET_POWER) < 0.06 else ""
        print(f"    {f*100:4.0f}%  power {p:4.2f}  {bar}{mark}")

    cen = rep["scenarios"][KEY]
    m, mid = cen["mde_popw"], float(np.mean(PLAUSIBLE_FRAC))
    if m is not None and m <= PLAUSIBLE_FRAC[0]:
        rep["decision"] = "GREEN-LIGHT B5d (robust) - detects even the conservative floor effect"
    elif m is not None and m <= mid:
        rep["decision"] = (f"GREEN-LIGHT B5d - the buildable {KEY} design (n_treated={cen['n_treated']}, "
                           f"real HRSA count) detects the LIKELY effect (MDE {m*100:.0f}% <= band "
                           f"midpoint {mid*100:.0f}%); needs TX assembly - NY-only (135) is upper-band "
                           f"only; underpowered only if the true effect is near the 2% floor")
    elif m is not None and m <= PLAUSIBLE_FRAC[1]:
        rep["decision"] = "BORDERLINE - detects only the optimistic upper band; widen the window/states"
    else:
        rep["decision"] = "DO NOT BUILD B5d - underpowered even pop-weighted; ship the null as the finding"
    print(f"\n  DECISION (central, pop-weighted): {rep['decision']}")
    print("  Honest reads: WLS only shrinks the SAMPLING noise, never the heterogeneity floor "
          f"(sqrt(a)={np.sqrt(noise.a):.0f}). CAVEAT (was overstated): this gate simulates a two-way-FE\n"
          "  DiD, but the shipped study runs Callaway-Sant'Anna, which uses only not-yet-treated\n"
          "  comparisons - strictly LESS efficient, so the realized CS MDE is LARGER than the TWFE MDE\n"
          "  here. Read this MDE as a LOWER bound and the FQHC null as possibly underpowered, not a clean\n"
          "  true null. (Spillover would still attenuate the true effect, making the gate stricter.)")
    return rep


if __name__ == "__main__":
    run()
