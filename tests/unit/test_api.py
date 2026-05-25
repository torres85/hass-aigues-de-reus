"""Unit tests for the Aigües de Reus API client."""
from __future__ import annotations

from datetime import date
from http.cookies import SimpleCookie
from unittest.mock import patch
from yarl import URL

import pytest
from aioresponses import aioresponses

from custom_components.aigues_de_reus.api import (
    AiguesDeReusClient,
    AiguesDeReusError,
    AuthError,
    ContractInfo,
)
from custom_components.aigues_de_reus.const import (
    API_BASE,
    CONTADORES_URL,
    LOGIN_URL,
)


@pytest.fixture
async def client():
    c = AiguesDeReusClient("12345678A", "secret")
    yield c
    await c.async_close()


def _ok_login(mocked: aioresponses) -> None:
    """Register the login POST returning 200."""
    mocked.post(LOGIN_URL, status=200, body="ok")


def _patch_auth_cookie(value: bool):
    """aioresponses doesn't propagate Set-Cookie, so we patch the cookie
    detection to simulate success/failure of the login."""
    return patch.object(
        AiguesDeReusClient, "_has_auth_cookie",
        staticmethod(lambda session: value),
    )


class TestLogin:
    async def test_login_success_sets_authed(self, client, login_html):
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            await client.async_login()

        assert client._authed is True

    async def test_login_failure_raises_auth_error(self, client, login_html):
        with aioresponses() as m, _patch_auth_cookie(False):
            m.get(LOGIN_URL, status=200, body=login_html)
            m.post(LOGIN_URL, status=200, body="bad credentials")
            # Follow-up GET when first POST has no cookie
            m.get(CONTADORES_URL, status=200, body="<html></html>")

            with pytest.raises(AuthError):
                await client.async_login()

        assert client._authed is False

    async def test_login_extracts_viewstate_fields(
        self, client, login_html
    ):
        """The POST body must include the hidden VIEWSTATE / EVENTVALIDATION."""
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            await client.async_login()

            # Inspect the POST request that was made
            posts = [
                req for key, reqs in m.requests.items()
                for req in reqs if key[0] == "POST"
            ]
            assert posts, "no POST request was made"
            post_body = posts[0].kwargs["data"]
            assert post_body["__VIEWSTATE"] == "VS_FAKE_TOKEN_xxxxx"
            assert post_body["__EVENTVALIDATION"] == "EV_FAKE_TOKEN_yyyyy"
            assert post_body["__VIEWSTATEGENERATOR"] == "ABC12345"
            assert post_body["dnn$ctr1331$View$textUsername"] == "12345678A"
            assert post_body["dnn$ctr1331$View$textPassword"] == "secret"
            assert post_body["__EVENTTARGET"] == "dnn$ctr1331$View$btnIniciarSesion"


class TestContractParsing:
    async def test_single_contract(self, client, login_html, contadores_html_single):
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            m.get(CONTADORES_URL, status=200, body=contadores_html_single)

            contracts = await client.async_get_contracts()

        assert len(contracts) == 1
        c = contracts[0]
        assert isinstance(c, ContractInfo)
        assert c.codigo_cliente == "1234567"
        assert c.contrato == "9999999"
        assert c.contador == "X11AB000001"
        assert "CARRER FALS" in c.direccion

    async def test_multi_contract(self, client, login_html, contadores_html_multi):
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            m.get(CONTADORES_URL, status=200, body=contadores_html_multi)

            contracts = await client.async_get_contracts()

        assert len(contracts) == 2
        active = next(c for c in contracts if c.contrato == "9999999")
        secondary = next(c for c in contracts if c.contrato == "8888888")
        assert active.codigo_cliente == "1234567"
        # Secondary contract has no codigo/contador (we don't postback)
        assert secondary.codigo_cliente == ""
        assert secondary.contador == ""
        assert "CARRER ALTRE" in secondary.direccion


class TestContadorParam:
    def test_returns_none_when_unset(self):
        c = AiguesDeReusClient("nif", "pw")
        assert c.contador_param is None

    def test_concatenates_three_parts(self):
        c = AiguesDeReusClient(
            "nif", "pw",
            codigo_cliente="111", contrato="222", contador="333",
        )
        assert c.contador_param == "111,222,333"


class TestApiCalls:
    @pytest.fixture
    async def authed_client(self):
        c = AiguesDeReusClient(
            "nif", "pw",
            codigo_cliente="111", contrato="222", contador="333",
        )
        c._authed = True  # skip login for these tests
        # Force the session to exist
        c._ensure_session()
        yield c
        await c.async_close()

    async def test_consumo_por_hora_builds_correct_url(
        self, authed_client, hourly_json_sample
    ):
        # aioresponses needs the full URL with query string
        full_url = (
            f"{API_BASE}/GetConsumoPorHoraTabla"
            "?contador=111,222,333&fecha=2026-05-21"
        )
        with aioresponses() as m:
            m.get(
                full_url,
                status=200,
                payload=hourly_json_sample,
                headers={"Content-Type": "application/json"},
            )
            rows = await authed_client.async_get_consumo_por_hora(date(2026, 5, 21))

        assert len(rows) == 24
        assert rows[7]["ConsumoM3"] == 0.007

    async def test_no_contract_raises(self):
        c = AiguesDeReusClient("nif", "pw")
        c._authed = True
        with pytest.raises(AiguesDeReusError, match="Contracte"):
            await c.async_get_consumo_por_hora(date(2026, 5, 21))
        await c.async_close()

    async def test_non_json_response_triggers_reauth(
        self, authed_client, login_html, hourly_json_sample
    ):
        """If the API returns HTML (session expired), the client must
        re-login and retry once."""
        api_url = (
            f"{API_BASE}/GetConsumoPorHoraTabla"
            "?contador=111,222,333&fecha=2026-05-21"
        )
        with aioresponses() as m, _patch_auth_cookie(True):
            # First call: HTML (login redirect)
            m.get(
                api_url,
                status=200,
                body="<html>login required</html>",
                headers={"Content-Type": "text/html"},
            )
            # Re-login flow
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            # Second attempt: JSON
            m.get(
                api_url,
                status=200,
                payload=hourly_json_sample,
                headers={"Content-Type": "application/json"},
            )

            rows = await authed_client.async_get_consumo_por_hora(date(2026, 5, 21))

        assert len(rows) == 24

    async def test_redirect_response_triggers_reauth(
        self, authed_client, login_html, hourly_json_sample
    ):
        api_url = (
            f"{API_BASE}/GetConsumoPorHoraTabla"
            "?contador=111,222,333&fecha=2026-05-21"
        )
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(api_url, status=302, headers={"Location": "/login"})
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            m.get(
                api_url,
                status=200,
                payload=hourly_json_sample,
                headers={"Content-Type": "application/json"},
            )

            rows = await authed_client.async_get_consumo_por_hora(date(2026, 5, 21))

        assert len(rows) == 24

    async def test_persistent_auth_failure_raises(self, authed_client, login_html):
        """If even after re-login the API still returns 302, raise AuthError."""
        api_url = (
            f"{API_BASE}/GetConsumoPorHoraTabla"
            "?contador=111,222,333&fecha=2026-05-21"
        )
        with aioresponses() as m, _patch_auth_cookie(True):
            m.get(api_url, status=302)
            m.get(LOGIN_URL, status=200, body=login_html)
            _ok_login(m)
            m.get(api_url, status=302)

            with pytest.raises(AuthError):
                await authed_client.async_get_consumo_por_hora(date(2026, 5, 21))
