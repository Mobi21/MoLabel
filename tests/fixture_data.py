from pathlib import Path

import pytest

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"

requires_benchmark_fixtures = pytest.mark.skipif(
    not any(FIXTURES_ROOT.glob("*/*/workbench/benchmarks")),
    reason=(
        "fixtures/**/workbench/benchmarks data is not checked in; "
        "tracked in https://github.com/Mobi21/MoLabel/issues/3"
    ),
)
