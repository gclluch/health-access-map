"""Pipeline orchestrator with stage idempotency + surgical re-runs (brief 12.4).

  python -m pipeline.run                      # full national build
  python -m pipeline.run --dev-state CA       # fast CA vertical slice
  python -m pipeline.run --only providers     # re-run one stage
  python -m pipeline.run --from acs           # re-run from a stage onward
  python -m pipeline.run --force              # ignore cached outputs
  python -m pipeline.run --cleanup            # delete the 10 GB NPPES CSV

Each stage writes its output and skips if it already exists (unless --force), so
the expensive NPPES extract/aggregate is a one-time cost across re-runs.
"""
from __future__ import annotations

import argparse
import time

from . import (build_acs, build_fqhc, build_gazetteer, build_geometry,
               build_geonames, build_lifeexp, build_outcomes, build_places,
               build_providers, build_supply, build_utilization, join_and_score,
               validate)
from .common import load_env, log
from .preflight import check as preflight_check

# ordered stages; geometry first (defines the ZCTA universe); supply + fqhc need
# acs + gazetteer; utilization needs geonames (county_fips); lifeexp + outcomes are
# independent outcomes; join merges everything; validate reads the joined metrics last.
STAGES = ["geometry", "places", "providers", "acs", "geonames",
          "gazetteer", "supply", "fqhc", "utilization", "lifeexp", "outcomes",
          "join", "validate"]
BUILDERS = {
    "geometry": build_geometry.build,
    "places": build_places.build,
    "providers": build_providers.build,
    "acs": build_acs.build,
    "geonames": build_geonames.build,
    "gazetteer": build_gazetteer.build,
    "supply": build_supply.build,
    "fqhc": build_fqhc.build,
    "utilization": build_utilization.build,
    "lifeexp": build_lifeexp.build,
    "outcomes": build_outcomes.build,
    "join": join_and_score.build,
    "validate": validate.build,
}


def run(dev_state, force, only, frm, do_preflight):
    load_env()
    if do_preflight and not preflight_check():
        log("run", "preflight failed; fix the above and re-run")
        raise SystemExit(1)

    if only:
        stages = [only]
    elif frm:
        stages = STAGES[STAGES.index(frm):]
    else:
        stages = STAGES

    scope = dev_state or "national"
    log("run", f"scope={scope} stages={stages} force={force}")
    for stage in stages:
        t0 = time.time()
        log("run", f"--- {stage} ---")
        # join builder has no dev_state arg signature difference; all accept (dev_state, force)
        BUILDERS[stage](dev_state=dev_state, force=force)
        log("run", f"--- {stage} done in {time.time()-t0:.1f}s ---")
    log("run", f"pipeline complete ({scope})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-state", default=None, help="filter every stage to one state, e.g. CA")
    ap.add_argument("--force", action="store_true", help="ignore cached outputs")
    ap.add_argument("--only", choices=STAGES, help="run a single stage")
    ap.add_argument("--from", dest="frm", choices=STAGES, help="run from a stage onward")
    ap.add_argument("--no-preflight", action="store_true")
    ap.add_argument("--cleanup", action="store_true", help="delete the extracted NPPES CSV and exit")
    args = ap.parse_args()

    if args.cleanup:
        build_providers.cleanup_extracted()
        return

    run(args.dev_state, args.force, args.only, args.frm, not args.no_preflight)


if __name__ == "__main__":
    main()
