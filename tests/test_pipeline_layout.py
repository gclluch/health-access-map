"""The pipeline/ vs pipeline/research/ split, locked.

`pipeline/` holds what `run.py` executes plus the shared libs it leans on; `pipeline/research/`
holds the one-offs run by hand (`make gate`, `make subcounty`, `make causal`, `make trends`, ...).
The `build_`/`validate_` prefixes do not carry that distinction - `validate.py` is a shipping
stage and `build_trends.py` is not - so the directory does, and this test keeps it true: a new
`build_*.py` dropped into `pipeline/` without a `run.py` stage fails here rather than becoming a
module nobody can tell is dead.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import run

PIPELINE = Path(__file__).resolve().parent.parent / "pipeline"

# Stages whose module is not named build_<stage>: the join and the terminal validation.
NON_BUILDER_STAGES = {"join", "validate"}


def test_every_builder_module_is_a_stage() -> None:
    modules = {p.stem[len("build_"):] for p in PIPELINE.glob("build_*.py")}
    assert modules == set(run.STAGES) - NON_BUILDER_STAGES


def test_every_stage_has_a_builder() -> None:
    assert set(run.STAGES) == set(run.BUILDERS)


def test_research_modules_are_not_imported_by_the_shipping_pipeline() -> None:
    """Nothing `run.py` touches may depend on a research one-off - that is what makes the
    research modules deletable without reading the build."""
    research = {p.stem for p in (PIPELINE / "research").glob("*.py")} - {"__init__"}
    offenders = [
        f"{p.name}: {name}"
        for p in PIPELINE.glob("*.py")
        for name in research
        if f"from .{name} import" in p.read_text() or f"from . import {name}" in p.read_text()
    ]
    assert not offenders, offenders
