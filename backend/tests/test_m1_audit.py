"""M1 verification: repository scaffold is importable and consistent.

These tests capture the M1 exit gate documented in IMPLEMENTATION_PLAN.md:
packages import cleanly, settings resolve sane defaults, and the planned
module layout exists so later milestones can land into an organized tree.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

PACKAGES = [
    "backend",
    "backend.api",
    "backend.data",
    "backend.graph",
    "backend.features",
    "backend.models",
    "backend.detection",
    "backend.risk",
    "backend.agents",
    "backend.explanations",
    "backend.evaluation",
    "backend.simulation",
    "backend.tests",
    "config",
]


@pytest.mark.parametrize("package_name", PACKAGES)
def test_package_imports(package_name: str) -> None:
    """Every planned top-level/backend package must import cleanly."""
    module = importlib.import_module(package_name)
    assert module is not None


def test_backend_version_exposed() -> None:
    import backend

    assert isinstance(backend.__version__, str)
    assert backend.__version__.count(".") == 2


def test_settings_defaults() -> None:
    """Settings resolve sane, env-overridable defaults and create dirs."""
    from config.settings import Settings

    s = Settings(seed=7, data_dir=Path("data"), db_path=Path("data/ringguard.db"))
    assert s.seed == 7
    assert s.api_title == "RingGuard AI Risk Manager"
    assert "SIMULATED" in s.api_description.upper()
    s.ensure_directories()
    assert s.data_dir.exists()
    assert s.db_path.parent.exists()


def test_milestone_plan_exists() -> None:
    """The implementation plan (M1 deliverable) must be present and complete."""
    root = Path(__file__).resolve().parents[2]
    plan = root / "IMPLEMENTATION_PLAN.md"
    assert plan.exists(), "IMPLEMENTATION_PLAN.md is the core M1 deliverable"
    text = plan.read_text(encoding="utf-8")
    # All 24 milestones referenced.
    for m in range(1, 25):
        assert f"**M{m}**" in text, f"milestone M{m} missing from plan"
    # Key protocol sections present.
    for heading in [
        "Leakage-Prevention",
        "Judge Demo",
        "Risk Register",
        "Definition of Done",
    ]:
        assert heading in text, f"missing plan section: {heading}"


def test_requirements_pins_core_stack() -> None:
    """requirements.txt pins the locally-verified backend toolchain."""
    root = Path(__file__).resolve().parents[2]
    reqs = (root / "requirements.txt").read_text(encoding="utf-8")
    for lib in ["fastapi", "pydantic", "networkx", "scikit-learn", "pytest", "numpy", "pandas"]:
        assert lib in reqs, f"{lib} missing from requirements.txt"