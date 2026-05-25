"""Constants for the Aigües de Reus integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "aigues_de_reus"
MANUFACTURER = "Aigües de Reus"

CONF_NIF = "nif"
CONF_PASSWORD = "password"
CONF_CONTRATO = "contrato"
CONF_CONTADOR = "contador"
CONF_CODIGO_CLIENTE = "codigo_cliente"
CONF_DIRECCION = "direccion"

BASE_URL = "https://www.aiguesdereus.cat"
LOGIN_URL = f"{BASE_URL}/es-es/Oficina-Virtual/Inicio-de-Sesi%C3%B3n"
CONTADORES_URL = f"{BASE_URL}/es-es/Oficina-Virtual/Consumos-y-Lecturas/Comptadors-Digitals"
API_BASE = f"{BASE_URL}/DesktopModules/OficinaVirtualServices/API/ConsultaContadoresDigitales"

UPDATE_INTERVAL = timedelta(hours=4)
HISTORICAL_DAYS = 3
INITIAL_BACKFILL_DAYS = 60

CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
CONF_BACKFILL_DAYS = "backfill_days"

DEFAULT_UPDATE_INTERVAL_HOURS = 4
MIN_UPDATE_INTERVAL_HOURS = 1
MAX_UPDATE_INTERVAL_HOURS = 24

DEFAULT_BACKFILL_DAYS = 60
MIN_BACKFILL_DAYS = 7
MAX_BACKFILL_DAYS = 180

SERVICE_FORCE_BACKFILL = "force_backfill"

LOGIN_BUTTON = "dnn$ctr1331$View$btnIniciarSesion"
LOGIN_USER_FIELD = "dnn$ctr1331$View$textUsername"
LOGIN_PASS_FIELD = "dnn$ctr1331$View$textPassword"
