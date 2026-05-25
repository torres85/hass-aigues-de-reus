"""Shared fixtures for the test suite."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# aiodns (transitive dep of aiohttp) requires SelectorEventLoop on Windows.
# pytest-homeassistant-custom-component sets up its own event loop policy, so
# we only force it when running pure unit tests (phacc plugin disabled).
_PHACC_ACTIVE = "pytest_homeassistant_custom_component.plugins" in sys.modules
if sys.platform == "win32" and not _PHACC_ACTIVE:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Ensure custom_components is importable as a top-level package
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def login_html() -> str:
    return (FIXTURES_DIR / "login_page.html").read_text(encoding="utf-8")


@pytest.fixture
def contadores_html_single() -> str:
    return (FIXTURES_DIR / "contadores_page_single.html").read_text(encoding="utf-8")


@pytest.fixture
def contadores_html_multi() -> str:
    return (FIXTURES_DIR / "contadores_page_multi.html").read_text(encoding="utf-8")


# A common API JSON response: 24 hours, mostly null with a few values
@pytest.fixture
def hourly_json_sample() -> list[dict]:
    rows = []
    for hour in range(24):
        consumo = None if hour < 6 or hour > 22 else round(0.001 * hour, 4)
        rows.append(
            {
                "Contrato": 9999999,
                "Contador": "X11AB000001",
                "Fecha": "2026-05-21T00:00:00",
                "Hora": hour,
                "ConsumoM3": consumo,
                "HorasLecturas": 1.0 if consumo is not None else None,
            }
        )
    return rows


@pytest.fixture
def hourly_json_empty() -> list[dict]:
    """Today's response from the portal — all nulls (data not yet published)."""
    return [
        {
            "Contrato": 9999999,
            "Contador": "X11AB000001",
            "Fecha": "2026-05-25T00:00:00",
            "Hora": h,
            "ConsumoM3": None,
            "HorasLecturas": None,
        }
        for h in range(24)
    ]


@pytest.fixture
def monthly_json_sample() -> list[dict]:
    return [
        {
            "Contrato": 9999999,
            "Contador": "X11AB000001",
            "Fecha": f"2026-05-{day:02d}T00:00:00",
            "DiaMes": day,
            "ConsumoM3": 0.1 * day,
            "HorasLecturas": 22.0,
        }
        for day in range(1, 6)
    ]
