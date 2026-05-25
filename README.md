# Aigües de Reus — Integració Home Assistant

Integració personalitzada per llegir el consum d'aigua de l'**Oficina Virtual d'Aigües de Reus** (`aiguesdereus.cat`) i mostrar-lo al panell d'energia de Home Assistant.

> ⚠️ Integració no oficial. Funciona fent ús de l'API interna del portal de clients (DotNetNuke). Si la companyia canvia la web, la integració pot deixar de funcionar fins que s'actualitzi.

## Què exposa

Per cada contracte configurat es creen aquests sensors:

| Sensor | `device_class` | `state_class` | Unitat | Ús al panell d'energia |
|---|---|---|---|---|
| Darrer consum horari | `water` | `measurement` | m³ | informatiu |
| Consum d'avui | `water` | `total_increasing` | m³ | informatiu |
| Consum d'aquest mes | `water` | `total_increasing` | m³ | informatiu |
| Lectura del comptador | `water` | `total_increasing` | m³ | _opcional_ |
| Última sincronització | `timestamp` | — | — | diagnòstic |
| Última lectura | `timestamp` | — | — | diagnòstic |

A més, la integració **importa estadístiques horàries** (mètric extern `aigues_de_reus:water_consumption_<contracte>`) directament al *recorder* de Home Assistant. **Aquesta és l'estadística que has d'afegir al panell d'energia** — mostra l'històric retroactiu sencer i no només des que vas instal·lar la integració.

## Instal·lació

### Via HACS (recomanat)
1. HACS → **Integracions** → ⋮ → **Custom repositories**.
2. Afegeix l'URL d'aquest repo, categoria *Integration*.
3. Cerca **Aigües de Reus** i instal·la.
4. Reinicia Home Assistant.
5. **Configuració → Dispositius i serveis → Afegir → Aigües de Reus** i introdueix NIF + contrasenya.

### Manual
Copia `custom_components/aigues_de_reus/` a `<config>/custom_components/` i reinicia.

## Panell d'energia

1. **Configuració → Panells → Energia → Aigua → Afegir consum**.
2. Tria l'estadística `Consum d'aigua (<el-teu-contracte>)`.
3. Opcional: defineix el preu per m³ per veure el cost.

## Granularitat

El portal proporciona dades horàries amb un **retard de fins a ~24h**. La integració actualitza cada 4 hores i fa fetch dels últims 4 dies a cada cicle, així es van omplint els valors a mesura que el portal els publica.

## Opcions configurables

Des de **Configuració → Dispositius i serveis → Aigües de Reus → Configurar**:

| Opció | Rang | Per defecte | Què fa |
|---|---|---|---|
| Interval d'actualització (hores) | 1-24 | 4 | Cada quant es consulta el portal |
| Dies d'històric a importar | 7-180 | 60 | Quants dies es baixen el primer cop o quan es força un backfill |

## Servei `force_backfill`

Re-importa les estadístiques horàries del període configurat. Útil si vols ampliar el rang històric o has perdut dades. **Eines de desenvolupament → Serveis → `aigues_de_reus.force_backfill`**.

## Limitacions actuals

- Si tens diversos contractes a la mateixa Oficina Virtual, només es pot vincular el contracte que estigui actiu al portal en el moment de la configuració. Per gestionar-ne d'altres, entra primer al portal i selecciona l'altre contracte abans d'afegir una nova entrada de la integració. *(En una versió futura es farà el postback automàticament.)*
- No es desa la contrasenya xifrada més enllà del que fa Home Assistant per defecte amb el `config_entry`.

## Tests

```bash
pip install -r requirements_test.txt
pytest
```

35 tests unitaris cobrint:
- **API client** (`test_api.py`, 89% cobertura): login DNN, parseig de contractes, re-auth per sessió expirada (302/HTML), construcció d'URLs.
- **Coordinator** (`test_coordinator.py`, ~50%): backfill complet vs. incremental, `running_sum`, cutoff per appendre només estadístiques noves, parseig dels timestamps del portal.
- **Config + Options flow** (`test_config_flow.py`, 98%): un i múltiples contractes, gestió d'errors, valors per defecte i persistència de les opcions.

CI a GitHub Actions corre `pytest` + `hassfest` + validació HACS a Linux a cada push i PR.

## Llicència

MIT
