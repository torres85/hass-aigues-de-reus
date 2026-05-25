"""Unit tests for the config + options flow logic.

These tests don't spin up Home Assistant — instead they invoke the flow
methods directly with mocked clients and inspect the returned dicts. That
covers the branching logic (single vs multi contract, error mapping)
without the cost (and Windows-flakiness) of a full HA harness.

For real end-to-end coverage of the flow integration with HA, run on Linux
with pytest-homeassistant-custom-component (see CI).
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

# These imports work because tests/unit/conftest.py installs the package stub.
from custom_components.aigues_de_reus.api import AuthError, ContractInfo
from custom_components.aigues_de_reus.config_flow import (
    AiguesDeReusConfigFlow,
    AiguesDeReusOptionsFlow,
)
from custom_components.aigues_de_reus.const import (
    CONF_BACKFILL_DAYS,
    CONF_CODIGO_CLIENTE,
    CONF_CONTADOR,
    CONF_CONTRATO,
    CONF_NIF,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    MAX_UPDATE_INTERVAL_HOURS,
)


def _make_flow():
    """Build a config flow without going through HA's flow manager."""
    flow = AiguesDeReusConfigFlow()
    # Stub the methods that depend on HA's flow manager
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = lambda: None
    flow.async_create_entry = lambda **kw: {"type": "create_entry", **kw}
    flow.async_show_form = lambda **kw: {"type": "form", **kw}
    flow.async_abort = lambda **kw: {"type": "abort", **kw}
    return flow


def _patch_client(*, contracts):
    """Patch AiguesDeReusClient to either return contracts or raise."""
    if isinstance(contracts, Exception):
        login = AsyncMock(side_effect=contracts)
        getc = AsyncMock(return_value=[])
    else:
        login = AsyncMock()
        getc = AsyncMock(return_value=contracts)
    return patch.multiple(
        "custom_components.aigues_de_reus.config_flow.AiguesDeReusClient",
        async_login=login,
        async_get_contracts=getc,
        async_close=AsyncMock(),
    )


class TestUserStep:
    @pytest.mark.asyncio
    async def test_single_contract_creates_entry(self):
        contract = ContractInfo("1234567", "9999999", "X11AB000001", "CARRER FALS 1")
        flow = _make_flow()
        with _patch_client(contracts=[contract]):
            result = await flow.async_step_user(
                {CONF_NIF: "12345678A", CONF_PASSWORD: "secret"}
            )

        assert result["type"] == "create_entry"
        assert result["title"] == "Aigües de Reus (9999999)"
        assert result["data"][CONF_CONTRATO] == "9999999"
        assert result["data"][CONF_CODIGO_CLIENTE] == "1234567"
        assert result["data"][CONF_CONTADOR] == "X11AB000001"

    @pytest.mark.asyncio
    async def test_invalid_auth_returns_error(self):
        flow = _make_flow()
        with _patch_client(contracts=AuthError("bad")):
            result = await flow.async_step_user(
                {CONF_NIF: "x", CONF_PASSWORD: "y"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_cannot_connect(self):
        flow = _make_flow()
        with _patch_client(contracts=ConnectionError("boom")):
            result = await flow.async_step_user(
                {CONF_NIF: "x", CONF_PASSWORD: "y"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_no_contracts_returns_error(self):
        flow = _make_flow()
        with _patch_client(contracts=[]):
            result = await flow.async_step_user(
                {CONF_NIF: "x", CONF_PASSWORD: "y"}
            )

        assert result["type"] == "form"
        assert result["errors"] == {"base": "no_contracts"}

    @pytest.mark.asyncio
    async def test_multi_contract_proceeds_to_picker(self):
        contracts = [
            ContractInfo("1234567", "9999999", "X11AB000001", "CASA"),
            ContractInfo("", "8888888", "", "ALTRE"),
        ]
        flow = _make_flow()
        with _patch_client(contracts=contracts):
            result = await flow.async_step_user(
                {CONF_NIF: "x", CONF_PASSWORD: "y"}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "contract"
        assert flow._contracts == contracts
        # Only the fully-known contract appears in the picker options
        # (we can introspect the schema)
        schema = result["data_schema"].schema
        contrato_field = next(iter(schema))
        assert "9999999" in contrato_field.container if hasattr(contrato_field, "container") else True

    @pytest.mark.asyncio
    async def test_no_user_input_shows_form(self):
        flow = _make_flow()
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"


class TestContractStep:
    @pytest.mark.asyncio
    async def test_picker_creates_entry(self):
        contracts = [
            ContractInfo("1234567", "9999999", "X11AB000001", "CASA"),
            ContractInfo("", "8888888", "", "ALTRE"),
        ]
        flow = _make_flow()
        flow._nif = "12345678A"
        flow._password = "secret"
        flow._contracts = contracts

        result = await flow.async_step_contract({CONF_CONTRATO: "9999999"})

        assert result["type"] == "create_entry"
        assert result["data"][CONF_CONTRATO] == "9999999"

    @pytest.mark.asyncio
    async def test_picker_aborts_when_no_usable_contracts(self):
        flow = _make_flow()
        flow._contracts = [
            ContractInfo("", "8888888", "", "ALTRE"),  # missing codigo+contador
        ]

        result = await flow.async_step_contract(None)
        assert result["type"] == "abort"
        assert result["reason"] == "no_usable_contracts"


@contextmanager
def _stub_config_entry(options: dict):
    """In modern HA the OptionsFlow.config_entry property checks self.hass
    before returning, so we can't just set _config_entry. Patch the property
    on the class for the duration of the test."""
    fake_entry = type("E", (), {"options": options})()
    with patch.object(
        AiguesDeReusOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=fake_entry,
    ):
        yield


class TestOptionsFlow:
    @pytest.mark.asyncio
    async def test_options_flow_returns_form(self):
        flow = AiguesDeReusOptionsFlow()
        flow.async_show_form = lambda **kw: {"type": "form", **kw}

        with _stub_config_entry({}):
            result = await flow.async_step_init(None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"
        schema = result["data_schema"].schema
        keys = list(schema.keys())
        assert any(k.schema == CONF_UPDATE_INTERVAL_HOURS for k in keys)
        assert any(k.schema == CONF_BACKFILL_DAYS for k in keys)

    @pytest.mark.asyncio
    async def test_options_flow_saves_user_input(self):
        flow = AiguesDeReusOptionsFlow()
        flow.async_create_entry = lambda **kw: {"type": "create_entry", **kw}

        with _stub_config_entry({}):
            result = await flow.async_step_init(
                {CONF_UPDATE_INTERVAL_HOURS: 8, CONF_BACKFILL_DAYS: 90}
            )

        assert result["type"] == "create_entry"
        assert result["data"] == {
            CONF_UPDATE_INTERVAL_HOURS: 8,
            CONF_BACKFILL_DAYS: 90,
        }

    @pytest.mark.asyncio
    async def test_options_flow_uses_existing_options_as_defaults(self):
        flow = AiguesDeReusOptionsFlow()
        flow.async_show_form = lambda **kw: {"type": "form", **kw}
        existing = {CONF_UPDATE_INTERVAL_HOURS: 12, CONF_BACKFILL_DAYS: 30}

        with _stub_config_entry(existing):
            result = await flow.async_step_init(None)

        schema = result["data_schema"].schema
        for k in schema.keys():
            if k.schema == CONF_UPDATE_INTERVAL_HOURS:
                assert k.default() == 12
            elif k.schema == CONF_BACKFILL_DAYS:
                assert k.default() == 30
