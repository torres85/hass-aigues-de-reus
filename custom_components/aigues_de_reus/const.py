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

# --- Tariff / cost estimation ---
# All values configurable via OptionsFlow. Defaults reflect the 2026 Reus
# rates (eBOPT 30.12.2025 + DOGC 9632 / Llei 3/2026 for the cànon).

CONF_TARIFF_ENABLED = "tariff_enabled"

CONF_WATER_FIXED_EUR_PER_DAY = "water_fixed_eur_per_day"
CONF_WATER_TIER1_EUR_PER_M3 = "water_tier1_eur_per_m3"
CONF_WATER_TIER1_LIMIT_M3 = "water_tier1_limit_m3"
CONF_WATER_TIER2_EUR_PER_M3 = "water_tier2_eur_per_m3"
CONF_WATER_TIER2_LIMIT_M3 = "water_tier2_limit_m3"
CONF_WATER_TIER3_EUR_PER_M3 = "water_tier3_eur_per_m3"

CONF_SEWER_FIXED_EUR_PER_DAY = "sewer_fixed_eur_per_day"
CONF_SEWER_TIER1_EUR_PER_M3 = "sewer_tier1_eur_per_m3"
CONF_SEWER_TIER1_LIMIT_M3 = "sewer_tier1_limit_m3"
CONF_SEWER_TIER2_EUR_PER_M3 = "sewer_tier2_eur_per_m3"
CONF_SEWER_TIER2_LIMIT_M3 = "sewer_tier2_limit_m3"
CONF_SEWER_TIER3_EUR_PER_M3 = "sewer_tier3_eur_per_m3"

CONF_CANON_FIXED_EUR_PER_DAY = "canon_fixed_eur_per_day"
CONF_CANON_TIER1_EUR_PER_M3 = "canon_tier1_eur_per_m3"
CONF_CANON_TIER1_LIMIT_M3 = "canon_tier1_limit_m3"
CONF_CANON_TIER2_EUR_PER_M3 = "canon_tier2_eur_per_m3"
CONF_CANON_TIER2_LIMIT_M3 = "canon_tier2_limit_m3"
CONF_CANON_TIER3_EUR_PER_M3 = "canon_tier3_eur_per_m3"

CONF_IVA_RATE = "iva_rate"
CONF_BILLING_PERIOD_START = "billing_period_start"
CONF_BILLING_PERIOD_DAYS = "billing_period_days"

DEFAULT_TARIFF_ENABLED = False

DEFAULT_WATER_FIXED_EUR_PER_DAY = 0.2640
DEFAULT_WATER_TIER1_EUR_PER_M3 = 0.4384
DEFAULT_WATER_TIER1_LIMIT_M3 = 0.0
DEFAULT_WATER_TIER2_EUR_PER_M3 = 0.0
DEFAULT_WATER_TIER2_LIMIT_M3 = 0.0
DEFAULT_WATER_TIER3_EUR_PER_M3 = 0.0

DEFAULT_SEWER_FIXED_EUR_PER_DAY = 0.1340
DEFAULT_SEWER_TIER1_EUR_PER_M3 = 0.0755
DEFAULT_SEWER_TIER1_LIMIT_M3 = 0.0
DEFAULT_SEWER_TIER2_EUR_PER_M3 = 0.0
DEFAULT_SEWER_TIER2_LIMIT_M3 = 0.0
DEFAULT_SEWER_TIER3_EUR_PER_M3 = 0.0

DEFAULT_CANON_FIXED_EUR_PER_DAY = 0.0329
DEFAULT_CANON_TIER1_EUR_PER_M3 = 0.5232
DEFAULT_CANON_TIER1_LIMIT_M3 = 0.0
DEFAULT_CANON_TIER2_EUR_PER_M3 = 0.0
DEFAULT_CANON_TIER2_LIMIT_M3 = 0.0
DEFAULT_CANON_TIER3_EUR_PER_M3 = 0.0

DEFAULT_IVA_RATE = 0.10
DEFAULT_BILLING_PERIOD_START = ""
DEFAULT_BILLING_PERIOD_DAYS = 60

LOGIN_BUTTON = "dnn$ctr1331$View$btnIniciarSesion"
LOGIN_USER_FIELD = "dnn$ctr1331$View$textUsername"
LOGIN_PASS_FIELD = "dnn$ctr1331$View$textPassword"
