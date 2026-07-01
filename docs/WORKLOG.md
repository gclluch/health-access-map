# Autonomous worklog

Rolling log of the overnight autonomous session. Newest first. Every entry is verified (tests pass /
measured) before commit. Rejections are progress too - they record what was tried and why it was dropped.

Discipline: measure before shipping, verify every change, never ship a broken/unverified result, commit
verified work in small units, re-evaluate priorities each cycle.

---

## Cycle 1
- **DONE** weights.json test side-effect: `test_validate_idempotent` now writes to a tmp path (monkeypatch), so it can't clobber the committed `frontend/public/weights.json`. Verified: passes, weights.json stays clean. Committed.
- **REJECTED (measured)** pop-weight tract-HPSA via HUD res_ratio xwalk: ~a wash. within-county 9.7%→11.0% (+1.3pt) BUT national r vs amenable 0.489→0.472 (worse), 0.973 correlated with area-weighting, coverage 71%→69%, and it adds a HUD-token dependency (fresh builds need $HUD_TOKEN). Not worth the token gate for a marginal, mixed change. Area-weighting stays.
- Next: surface the measured within-county % in the UI (the honesty move the user asked for), then VALIDATION §7 regen, dep pinning.

## Cycle 0 - baseline (session start)
- Done this session already (committed + pushed, 8 commits): full-repo audit remediation, copy de-slop,
  §2.3 psychiatric-NP reclassification, §3.1 spatial county-block causal CIs, §3.2 unweighted anchored
  weights, tract-level HPSA (§ sub-county), tract-HPSA kernel test, CI data-slice fixture (row-level
  acceptance+integrity guards now RUN in CI).
- Baseline: 132 py tests + 51 frontend tests pass; tsc clean.
- Deploy blocked on user's Netlify auth (read-only token).

### Queue (re-evaluated each cycle)
1. weights.json test side-effect (test writes a committed artifact) - quick correctness.
2. Pop-weight tract-HPSA via HUD res_ratio xwalk (on disk) - measure-first for more within-county lift.
3. VALIDATION.md §7 CIs stale vs county-block numbers - regenerate.
4. Dep pinning (reproducible builds).
5. medical_debt: down-weight or caveat (last county-flat scored input).
6. Surface sub-county resolution % in the UI (honesty move).
7. Audit tail (remaining mediums/lows in docs/AUDIT.md).

## Cycle 2
- **DONE** sub-county disclosure in UI: added a quantified limitations point to the methodology ("~24% of variation within-county; health need ~31%, care access ~9%; HPSA now tract-resolved, medical debt the remaining county-flat input"). Verified in browser. Committed.
- **DONE** dep pinning: CI now installs `requirements.lock` (exact) not floating `requirements.txt`; backend image pins fastapi/uvicorn/pandas/pyarrow to exact versions. Verified pins match the installed+tested versions. Committed.
- medical_debt: no free sub-county source; keeping it (valuable between-county signal) and caveating via the new UI point = the honest resolution. No code change.
- Next: audit-tail correctness sweep (verify which flagged frontend/pipeline items are still real, fix those).

## Cycle 3
- **CONFIRMED (measured)** sub-county signal is real: composite within-county r vs life expectancy = **-0.503**, county-block CI [-0.526,-0.480] (excludes 0), correctly signed. Amenable/infant mortality within-county = 0.000 exactly (county-level outcomes, no within-county variance to test) - the honest caveat. VALIDATION §3 already documents sub-county validity, so this confirms rather than adds.
- **§5.5 = non-issue**: severity()/band() are fed percentile-converted values at every call site (not the raw CLT-compressed composite). Audit flagged a risk callers actually avoid. No change.
- **DONE** VALIDATION §7f headline updated to the county-block CI (null, not "borderline"), consistent with the §3.1 code + the note. Committed.

## Cycle 4
- **DONE (important)** tract-HPSA doc footprint: my §sub-county change overturned a documented finding ("HPSA carries ~zero sub-county signal / county-constant") woven through VALIDATION §3-§6 (repeated 5x). Fixed the prominent §3 "5 A's" table (HPSA within-county 0.000→+0.20) + finding + the county-flat paragraph (now medical_debt-only); added a §3 banner flagging that later computed tables (§6a/§6b) still say "HPSA county-constant" and predate the fix (need a validate_subcounty regen). Committed.
- Lesson: a shipped DATA change can invalidate a whole documented analysis thread - always sweep the docs for the superseded claim.
- Testing whether a full validate_subcounty.run_national() regen is feasible offline (to properly refresh the computed tables).

## Cycle 5
- **DONE** ran validate_subcounty.run_national() OFFLINE (works from local caches) -> authoritative regenerated within-county r's on the new tract-HPSA metrics. HPSA = **+0.246** (was 0.000); provider_supply 0.076 + insurance 0.477 match the doc exactly (confirms the doc table was from this function). Updated §3 to +0.246 and corrected the "HPSA county-constant" prose (§overdose). Computed §6a/§6b tables still flagged by the §3 banner (need their specific state analyses re-run).
- Next: verify the CI changes end-to-end (fresh venv + requirements.lock + fixture path) - the real CI scenario, to catch any break before the user's CI runs.

## Cycle 6
- **DONE (major verification)** CI end-to-end sim: fresh clone (no gitignored data → fixture path) + `pip install requirements.lock` + pytest = **101 passed, 31 skipped**. Confirms the CI dep-pinning + data-slice changes work in a clean env exactly as GitHub Actions runs them. Before: 0 data-gated guards ran; now 101 run.
- **DONE** METHODOLOGY correction: the "sub-county HPSA resolution is a wash (0.99 corr with county-max)" + "spatial-signal ceiling reached" claims tested only the NAIVE form. The tract-component form (county-wide fallback) shipped this build and wins (0.000→+0.246 within-county, validation ~doubled). Corrected both. A genuine finding - the prior verdict missed the right construction.
- Net: the tract-HPSA change is now fully integrated (code + test + CI-guarded + VALIDATION + METHODOLOGY + UI). 

## Cycle 7
- **DONE (honest reconciliation)** DECISIONS.md: a PRIOR project analysis had concluded sub-county HPSA was "below ship bar" (+0.089 *marginal* additive within-county). I shipped it - so I reconciled truthfully: the ship is on CORRECTNESS (county-MAX broadcasts a county's worst tract to all its ZCTAs = wrong geography; HPSA's own validation r doubled 0.25→0.49; within-county sign flips to correct), NOT a within-county-signal win (marginal stays ~+0.089, composite moves <1pt). The prior verdict was right about *signal*; it missed that the old form was wrong enough to fix regardless. Also fixed medical_debt's "like HPSA" parenthetical.
- Doc-consistency sweep for tract-HPSA now COMPLETE: VALIDATION §3+overdose, METHODOLOGY (2 spots), DECISIONS (2 spots), UI methodology point - all consistent + honest. Computed §6a/§6b tables flagged by the §3 banner.
- Re-eval: tract-HPSA fully integrated + honestly documented. Diminishing returns on it. Next cycle: shift to a different area (code robustness or a genuine new improvement).

## Cycle 8
- **Verified NON-BUGS** (earnest re-eval of audit flags): §5.5 (severity/band fed raw composite) - callers all pass percentile-converted values; §6.13 (Legend vs MapView scale drift) - both collect scale values identically, no live divergence. Frontend is more correct than the audit's risk flags implied. No changes needed.
- Trying to COMPLETE the §6 VALIDATION doc fix (overdose/state tables still say "HPSA county-constant") by regenerating offline rather than leaving them banner-flagged.

## Cycle 9
- **DONE (real reproducibility fix, §2.5)** build_acs SVI fetch: a failed scored input (crowding, mobile_home, multi_unit, no_hs, no_vehicle, unemployment) was caught+logged+skipped -> a silently different, degraded, non-deterministic composite between runs. Now dies loudly for scored inputs; still skips the 6 context-only ones (pct_minority, medicaid_rate, etc.). Scored set computed from the taxonomy so it self-updates. Parses + split verified; safe-by-inspection (silent-degrade -> loud-fail; doesn't break the current build since Census was up when it built).
- Also confirmed the overdose validator runs offline -> HPSA within-county vs overdose = +0.136 (was ~0), a 2nd independent outcome confirming the tract-HPSA gain. §6 CA/TX state tables stay banner-flagged (need their state runs; low marginal value).

## Cycle 10
- **DONE (robustness, §2.10/§2.11)** build_broadband: added a 3-try retry for transient Census 5xx/key-lag (was a single request that died on any hiccup), and a distribution guard (median 0.02-0.45) so a future ACS renumber of the hard-indexed B28002_013 fails loudly instead of shipping a wrong rate. Parses; guard accepts the real data (median 0.093).
- Honest re-eval: the high+medium-value solo-verifiable items are largely done. Remaining audit items are low-value builder-robustness or need a live pipeline build (network) / the user (deploy) to verify. Next: verify reproducibility itself (the theme of the recent fixes) - rebuild the scoring twice and confirm determinism; that both validates the fixes and could surface a real non-determinism bug.

## Cycle 11
- **VERIFIED** scoring determinism: rebuilt join_and_score and compared all 181 columns of metrics.parquet - byte-stable, including access_gap_rank_lo/hi (the np.random reliable-range band, confirming it's seeded). The composite is fully reproducible; the §2.5/§2.10-11 fixes protect a genuinely deterministic pipeline. No bug found (verification is progress).

## Cycle 12
- **DONE (robustness, §2.13)** build_gazetteer: the HEAD pre-gate skipped a Census vintage whenever the server rejects HEAD (405/403) but would serve GET. Removed it - download_file's GET + min_bytes validation is the honest test and already caches/raises correctly. Net simpler + more robust; removed the now-dead httpx import. Imports clean.

## Cycle 13
- **DONE (causal rigor, audit §3)** FQHC power gate overclaimed "TWFE MDE ~= CS MDE" - but the shipped Callaway-Sant'Anna uses only not-yet-treated comparisons (strictly less efficient), so its realized MDE is LARGER. Corrected the gate's printed "Honest reads" + VALIDATION §7g: the FQHC null is now framed as **suggestive-but-underpowered** (right-signed, dose-responsive, wide CI), not a cleanly-powered true null. A meaningful honesty fix - one of the remaining HIGH causal audit items. Parses.
- Full suite still 132 pass (builder cycles 8-12 no regression).

## Cycle 14
- **MILESTONE** all HIGH-severity audit findings resolved (fixed / measured-rejected / already-disclosed). Causal §4 multiplicity is already honestly disclosed in VALIDATION §4a (winner's-curse, "exact decimal is soft", "none of these is a multiplicity correction") - the formal fix is a research-process change, not a retrofit. Consolidated the full status in AUDIT.md.
- Now in MEDIUM/LOW territory. Continuing with genuinely-useful items, transparent about value level.

## Cycle 15
- **DONE (type safety, §5.13)** removed SlimMetric's blanket `[k: string]` index signature - a typo'd column (m.halth_need_pctile) was silently `null` at runtime; now a compile error. Blast radius was only 3 dynamic-access sites (scoring.metricValue, store lazy-merge, DetailPanel sub-score pctile), each fixed with a documented unknown-bridged cast. tsc clean + 51 tests pass. Purely type-level, no runtime change.

## Cycle 16
- **DONE (honesty, §1.5)** build_supply shortage flag: primary_people_per_provider is 1/(Gaussian-decayed E2SFCA), a DECAY-WEIGHTED proxy - not the hard population-per-provider service-area ratio the HRSA 3,500:1 threshold is literally defined on. Relabeled the comment, provenance shortage_basis, and log to "E2SFCA proxy ~ HRSA 3,500:1" so it doesn't overclaim the official designation. Frontend already caveats "spatial access, not an HPSA designation" - left as-is. Parses.

## Cycle 17
- **DONE (robustness, §2.11)** build_trends poverty fetch: added the same 3-try retry as broadband (was a single request that died on any transient Census hiccup). Parses. Completes the broadband/trends pair; a 4th duplication would justify factoring _census_get into common, but 2 is under the abstraction threshold.
- Note: builder retry now in broadband + trends; build_acs already has its own _census_get retry.

## Cycle 18
- **VERIFIED** committed weights.json is current: regenerated the anchored presets via validate.build() on the tract-HPSA metrics -> byte-identical to committed. The tract-HPSA change to care_access didn't shift the floor-weighted correlation presets enough to change the rounded weights. (Checked because cycle-1 redirected the idempotency test's write to tmp, so nothing auto-refreshes the committed file - but it wasn't stale.) No change needed.

## Cycle 19
- **VERIFIED** accessibility: audited every interactive control in the live app - all buttons/comboboxes/inputs have accessible names (aria-label / title / non-aria-hidden text), incl. an aria-hidden-aware check. Combined with the earlier SearchBox/Tip aria + modal-inert fixes, a11y is solid. No gap found (confirmation is progress).

## Honest checkpoint (after 19 cycles, ~30 commits, all pushed)
State: the HIGH + MEDIUM-value verifiable work is COMPLETE. All HIGH audit findings resolved; last real MEDIUM (§5.13) done; reproducibility fixed + verified deterministic; CI verified end-to-end; docs consistent + honest; weights.json + a11y confirmed good. Remaining items are genuinely LOW-value (cosmetic frontend, marginal builder hygiene, null-study data cleanup) or BLOCKED (deploy = user's Netlify auth) or LARGE (formal multiplicity framework - already honestly disclosed; MapView autoHighlight - visual, hover already snappy). Continuing with genuine low-value items + verification, transparent about the tail. Top remaining ACTION is the user's deploy.

## Cycle 20
- **MEASURED -> honest caveat (§2.6)** FQHC treatment-group "reopening contamination": measured the source - HRSA's file has 0 inactive sites (all 18,764 active), so it doesn't retain closed sites. The contamination is UNDETECTABLE with this data (the audit's "use full history incl. inactive" fix is impossible - there's no inactive history), and rare. Corrected the code's "FIRST EVER" overclaim to "first-among-still-active" with the honest caveat. Not a fixable bug; a data limitation, now documented.

## Cycle 21
- **MEASURED -> negligible (§1.9)** reliable-range band centering: band samples uniform(0.15,0.55) ~ equal weights, point uses 0.35/0.30/0.35. Measured: point inside its own band 99.9%, offset from band center mean +0.03 / median -0.05 pctile pts (no systematic bias) - because the shipped weights ~ equal. Centering the band draw on the exact weights would change nothing measurable. Rejected.

## Cycle 22
- **MEASURED -> accept (§1.10)** multiplicative-lens floor (frac clipped to 0.01): only 2.55% of ZCTAs hit the floor in >=1 dimension, and the displayed access_gap_mult_pctile stays well-differentiated (298 distinct values in [0,3]) because the final _pct re-rank spreads them - no severe compression. Secondary selectable lens, documented rationale. No change.

## Statistical-rigor sweep COMPLETE
Every marginal statistical concern from the audit has now been measure-first assessed:
- FIXED: §3.1 spatial CIs, §3.2 weights, §3.14 bootstrap p-floor, §2.5 SVI reproducibility, FQHC power caveat, tract-HPSA.
- MEASURED -> negligible/rejected (not shipped): §1.1 percentile universe (0.11pt), §1.9 band centering (offset ~0), pop-weighted HPSA (wash), naive tract-hybrid (wrong-signed).
- MEASURED -> accept as-is: §1.10 mult floor (modest, mitigated).
- Already honestly disclosed: §4 multiplicity (winner's curse, §4a).
The index's statistical concerns are now either corrected or rigorously confirmed negligible - the honest, defensible state.
