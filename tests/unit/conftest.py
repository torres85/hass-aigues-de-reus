"""Conftest for pure unit tests.

These tests don't need a full Home Assistant instance. We stub the
``custom_components.aigues_de_reus`` package so importing the submodules
(api.py, coordinator.py) doesn't run __init__.py — which pulls in voluptuous,
ServiceCall and friends, all heavy HA-only deps that aren't needed here.

Integration tests in tests/integration/ deliberately skip this stub so that
pytest-homeassistant-custom-component sees the real package.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_stub_pkg = "custom_components.aigues_de_reus"
if _stub_pkg not in sys.modules:
    parent_pkg_name = "custom_components"
    if parent_pkg_name not in sys.modules:
        parent = types.ModuleType(parent_pkg_name)
        parent.__path__ = [str(ROOT / parent_pkg_name)]
        sys.modules[parent_pkg_name] = parent
    pkg = types.ModuleType(_stub_pkg)
    pkg.__path__ = [str(ROOT / "custom_components" / "aigues_de_reus")]
    sys.modules[_stub_pkg] = pkg
