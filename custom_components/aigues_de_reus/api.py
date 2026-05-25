"""API client for Aigües de Reus Oficina Virtual."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    API_BASE,
    CONTADORES_URL,
    LOGIN_BUTTON,
    LOGIN_PASS_FIELD,
    LOGIN_URL,
    LOGIN_USER_FIELD,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class AiguesDeReusError(Exception):
    """Base error."""


class AuthError(AiguesDeReusError):
    """Authentication failed."""


@dataclass
class ContractInfo:
    codigo_cliente: str
    contrato: str
    contador: str
    direccion: str | None = None


class AiguesDeReusClient:
    """Async client for the Aigües de Reus customer portal.

    Owns its own aiohttp ClientSession with a private cookie jar so that the
    DNN auth cookie can't be clobbered by the shared HA session.
    """

    def __init__(
        self,
        nif: str,
        password: str,
        *,
        codigo_cliente: str | None = None,
        contrato: str | None = None,
        contador: str | None = None,
    ) -> None:
        self._nif = nif
        self._password = password
        self._authed = False
        self._lock = asyncio.Lock()
        self.codigo_cliente = codigo_cliente
        self.contrato = contrato
        self.contador = contador
        # Private session. Cookie jar lives inside it; aiohttp will manage
        # Set-Cookie automatically on every request.
        self._session: aiohttp.ClientSession | None = None

    @property
    def contador_param(self) -> str | None:
        if self.codigo_cliente and self.contrato and self.contador:
            return f"{self.codigo_cliente},{self.contrato},{self.contador}"
        return None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT},
                cookie_jar=aiohttp.CookieJar(),
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def async_close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> None:
        """Perform DNN/ASP.NET WebForms login. Sets .DOTNETNUKE auth cookie."""
        async with self._lock:
            session = self._ensure_session()
            session.cookie_jar.clear()

            async with session.get(LOGIN_URL) as resp:
                resp.raise_for_status()
                html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            form_fields = self._extract_hidden_fields(soup)

            rvt_value = form_fields.get("__RequestVerificationToken", "")
            for cookie in session.cookie_jar:
                if cookie.key == "__RequestVerificationToken":
                    rvt_value = cookie.value
                    break

            data = {
                **form_fields,
                "ScriptManager": f"dnn$ctr1331$dnn$ctr1331$View_UPPanel|{LOGIN_BUTTON}",
                "__EVENTTARGET": LOGIN_BUTTON,
                "__EVENTARGUMENT": "",
                LOGIN_USER_FIELD: self._nif,
                LOGIN_PASS_FIELD: self._password,
                "__RequestVerificationToken": rvt_value,
                "__ASYNCPOST": "true",
                "RadAJAXControlID": "dnn_ctr1331_View_UP",
            }

            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "Origin": "https://www.aiguesdereus.cat",
                "Referer": LOGIN_URL,
            }

            async with session.post(
                LOGIN_URL, data=data, headers=headers, allow_redirects=False
            ) as resp:
                body = await resp.text()
                _LOGGER.debug(
                    "Login POST status=%s len=%d", resp.status, len(body)
                )

            if not self._has_auth_cookie(session):
                # Some DNN flows publish the auth cookie only on a follow-up GET
                async with session.get(CONTADORES_URL, allow_redirects=True) as r2:
                    _LOGGER.debug(
                        "Login follow-up GET %s -> %s", r2.url, r2.status
                    )

            if not self._has_auth_cookie(session):
                _LOGGER.debug(
                    "Cookies after login attempt: %s",
                    [c.key for c in session.cookie_jar],
                )
                raise AuthError(
                    "Login fallit: credencials incorrectes o portal canviat"
                )

            self._authed = True
            _LOGGER.debug("Login OK")

    @staticmethod
    def _has_auth_cookie(session: aiohttp.ClientSession) -> bool:
        return any(c.key == ".DOTNETNUKE" and c.value for c in session.cookie_jar)

    @staticmethod
    def _extract_hidden_fields(soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}
        for inp in soup.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            if not name:
                continue
            fields[name] = inp.get("value", "")
        return fields

    async def async_get_contracts(self) -> list[ContractInfo]:
        """Fetch the contadors page and parse the available contracts."""
        if not self._authed:
            await self.async_login()

        html = await self._get_html(CONTADORES_URL)
        soup = BeautifulSoup(html, "html.parser")

        contracts: list[ContractInfo] = []

        hid = soup.find("input", {"id": "hidContador"})
        select = soup.find(
            "select", attrs={"name": lambda n: n and "Contrato" in n}
        )

        if hid and hid.get("value"):
            parts = hid["value"].split(",")
            if len(parts) == 3:
                cod_cli, contrato, contador = parts
                direccion = None
                if select:
                    opt = select.find("option", {"value": contrato})
                    if opt:
                        text = opt.get_text(strip=True)
                        if "(" in text:
                            direccion = text.split("(", 1)[1].rstrip(")")
                contracts.append(
                    ContractInfo(cod_cli, contrato, contador, direccion)
                )

        if select:
            for opt in select.find_all("option"):
                value = opt.get("value", "").strip()
                if not value or value == ":":
                    continue
                if any(c.contrato == value for c in contracts):
                    continue
                text = opt.get_text(strip=True)
                direccion = (
                    text.split("(", 1)[1].rstrip(")") if "(" in text else None
                )
                contracts.append(
                    ContractInfo(
                        codigo_cliente="",
                        contrato=value,
                        contador="",
                        direccion=direccion,
                    )
                )

        return contracts

    async def _get_html(self, url: str) -> str:
        session = self._ensure_session()
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _api_get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """Call a JSON API endpoint, re-auth on session expiry."""
        url = f"{API_BASE}/{endpoint}"
        for attempt in (1, 2):
            if not self._authed:
                await self.async_login()
            session = self._ensure_session()

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": CONTADORES_URL,
            }
            try:
                async with session.get(
                    url, params=params, headers=headers, allow_redirects=False
                ) as resp:
                    body_preview = ""
                    if resp.status in (302, 301, 401, 403):
                        _LOGGER.debug(
                            "API %s -> %s, re-auth needed (attempt %d)",
                            endpoint, resp.status, attempt,
                        )
                        self._authed = False
                        if attempt == 1:
                            continue
                        raise AuthError(f"Sessió expirada ({resp.status})")
                    resp.raise_for_status()
                    ctype = resp.headers.get("Content-Type", "")
                    if "application/json" not in ctype:
                        body_preview = (await resp.text())[:200]
                        _LOGGER.warning(
                            "API %s tornà %s (no JSON): %r",
                            endpoint, ctype, body_preview,
                        )
                        self._authed = False
                        if attempt == 1:
                            continue
                        raise AiguesDeReusError(
                            f"Resposta no-JSON inesperada ({ctype}): {body_preview!r}"
                        )
                    return await resp.json()
            except aiohttp.ClientResponseError as err:
                if err.status in (401, 403) and attempt == 1:
                    self._authed = False
                    continue
                raise AiguesDeReusError(
                    f"Error HTTP {err.status} a {endpoint}"
                ) from err
        raise AiguesDeReusError("Crida API fallida")

    async def async_get_consumo_por_hora(self, fecha: date) -> list[dict[str, Any]]:
        if not self.contador_param:
            raise AiguesDeReusError("Contracte no configurat")
        return await self._api_get(
            "GetConsumoPorHoraTabla",
            {"contador": self.contador_param, "fecha": fecha.isoformat()},
        )

    async def async_get_consumo_mensual(
        self, anio: int, mes: int
    ) -> list[dict[str, Any]]:
        if not self.contador_param:
            raise AiguesDeReusError("Contracte no configurat")
        return await self._api_get(
            "GetConsumoMensualTabla",
            {"contador": self.contador_param, "anio": anio, "mes": mes},
        )

    async def async_get_lecturas_diarias(self, fecha: date) -> list[dict[str, Any]]:
        if not self.contador_param:
            raise AiguesDeReusError("Contracte no configurat")
        return await self._api_get(
            "GetLecturasDiariasTabla",
            {"contador": self.contador_param, "fecha": fecha.isoformat()},
        )
