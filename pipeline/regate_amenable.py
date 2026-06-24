"""regate_amenable: one-step finish for the amenable-mortality anchor.

Amenable (treatable) mortality is the one access-sensitive outcome that can LEGITIMATELY
weight care access - all-cause mortality is need-dominated and starves it by construction
(docs/VALIDATION.md). The whole pipeline is wired for it; the only manual step is the CDC
WONDER county export (the recipe + the encoded OECD ICD-10 set are in build_amenable.py),
because WONDER's API serves national data only.

Once you have saved the export to data/raw/wonder_amenable_county.txt, run:

    python -m pipeline.regate_amenable          # or: make amenable

It parses the export, re-merges outcomes, re-scores, re-derives the anchored weights, and
prints the standard gate PLUS the amenable-mortality focus (care-access marginal value +
partial r vs treatable mortality, with cluster-bootstrap CIs). Nothing else is needed.
"""
from __future__ import annotations

from . import (bootstrap_gate, build_amenable, build_outcomes, config, diagnostics,
               join_and_score, validate)
from .common import log


def main() -> None:
    export = build_amenable.WONDER_RAW
    csv = config.RAW / "amenable_mortality_county.csv"
    if not export.exists() and not csv.exists():
        print(f"No WONDER export at {export}")
        print("and no parsed CSV at", csv)
        print()
        print("Pull it first: the 10-minute WONDER recipe and the encoded OECD treatable")
        print("ICD-10 set are in pipeline/build_amenable.py (module docstring). Save the")
        print(f"tab-delimited export to {export}, then re-run this.")
        return

    log("regate", "1/6 build_amenable - parse the WONDER export")
    build_amenable.build()
    log("regate", "2/6 build_outcomes - re-merge outcomes with amenable (force)")
    build_outcomes.build(force=True)
    log("regate", "3/6 join_and_score - re-score, carrying the amenable column")
    join_and_score.build()
    log("regate", "4/6 validate - re-derive anchored weights (now incl. amenable)")
    validate.build()
    log("regate", "5/6 diagnostics - north-star gate (now incl. amenable outcome)")
    diagnostics.run()
    log("regate", "6/6 bootstrap_gate - CIs + the amenable-mortality focus")
    bootstrap_gate.run()
    log("regate", "done - see the AMENABLE-MORTALITY FOCUS block above for the care-access verdict")


if __name__ == "__main__":
    main()
