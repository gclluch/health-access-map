"""Research one-offs: modules run by hand (`make gate`, `make subcounty`, `make causal`, ...),
never by `pipeline.run`. Nothing here feeds `metrics.parquet` - the split is ships vs doesn't,
which the `build_`/`validate_` prefixes used to obscure. `tests/test_integrity.py` locks it:
every `pipeline/build_*.py` must be a `run.py` stage.
"""
