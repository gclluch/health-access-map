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
