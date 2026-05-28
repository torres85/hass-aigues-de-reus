# Aigües de Reus

Integració per Home Assistant que llegeix el consum d'aigua de l'Oficina Virtual d'**Aigües de Reus** i l'integra al **panell d'energia**.

- Sensors de consum horari, diari i mensual
- Lectura del comptador digital
- Importació d'estadístiques horàries retroactives → l'històric apareix al panell d'energia des del primer dia que tinguis dades al portal
- Suporta múltiples contractes (un per *config entry*)
- 🆕 **Estimació de costos (€)** opcional, totalment configurable des del flow d'opcions: 3 trams per concepte (aigua/claveguera/cànon), IVA, període de facturació amb auto-roll. Defaults amb les tarifes 2026 de Reus.
- 🆕 **Cost integrat al panell d'energia** com a estadística externa (`aigues_de_reus:water_cost_<contracte>`) — el dashboard recalcula correctament per qualsevol finestra (avui, setmana, mes, etc.).

Cal NIF + contrasenya de la teva Oficina Virtual.
