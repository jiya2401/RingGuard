"""Shared pytest fixtures for the data generator."""

from __future__ import annotations

import pytest

from backend.data.config import tiny_config
from backend.data.generator import build_ecosystem


@pytest.fixture(scope="session")
def tiny_ecosystem():
    """A fast, deterministic, small ecosystem for unit tests."""
    return build_ecosystem(tiny_config(), seed=7)


@pytest.fixture(scope="session")
def tiny_cfg():
    return tiny_config()


def entity_index(ecosystem):
    """entity_id -> Entity for quick lookups."""
    return {e.entity_id: e for es in ecosystem.entities.values() for e in es}