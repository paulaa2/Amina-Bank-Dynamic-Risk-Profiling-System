# Amina Bank — Dynamic Risk Profiling System

Motor de **Perpetual KYC (pKYC)** para el reto AMINA Bank en **SwissHacks 2026**.

Combina inteligencia pública en tiempo real (Layer 1) con perfiles internos de KYC (Layer 2) para detectar **KYC Drift**: desviaciones estructurales, semánticas y transaccionales respecto al onboarding original del cliente.

---

## Problema que resuelve

Los sistemas KYC tradicionales revisan clientes de forma calendarizada (p. ej. cada 3 años). Eso deja al banco ciego ante cambios de modelo de negocio, reestructuraciones societarias y señales adversas en el dominio público que aparecen meses antes de una alerta AML transaccional.

Este motor monitoriza de forma continua tres dimensiones de riesgo:

| Dimensión | Qué detecta |
|---|---|
| **Semántica** | Cambio de modelo de negocio (noticias, web, registros) |
| **Topológica** | Cambios en directores, accionistas, bucles de propiedad, contagio desde entidades sancionadas |
| **Transaccional** | Anomalías cuantitativas en flujos de fondos (Z-Score) |

---

## Arquitectura

```
Layer 1 (público)          Layer 2 (interno)
     │                            │
     └──────────┬─────────────────┘
                ▼
     [Enmascaramiento GDPR]
                ▼
     [Resolución de entidades]
                ▼
     ┌──────────┴──────────┐
     ▼                     ▼
 [Drift semántico]   [Grafo topológico]
 Page-Hinkley         NetworkX + contagio
     └──────────┬──────────┘
                ▼
     [Fusión multicorriente + Bonferroni]
                ▼
     [Informe AML + doble autorización]
```

**Stack principal:** Page-Hinkley (concept drift) · NetworkX (contagio dirigido) · embeddings + distancia coseno · LLM solo en casos de alto riesgo.

---

## Estructura del repositorio

El repositorio separa de forma estricta la **capa de datos** (recolección
desde fuentes públicas / APIs) del **motor de inteligencia** (la lógica pKYC).
Ambas se comunican únicamente a través de la base de datos SQLite.

```
.
├── README.md
├── requirements.txt
├── data/
│   └── risk_profiling.db          # base de datos generada por la capa de datos
├── docu/
│   ├── final_implementation.md    # especificación técnica completa
│   └── info_challenge.md          # descripción oficial del reto
├── scripts/                       # CAPA DE DATOS (Layer 1 + Layer 2)
│   ├── collectors/                # Google News RSS, OpenSanctions, GLEIF, RDAP...
│   ├── models.py · db.py          # esquema SQLAlchemy + sesión
│   ├── seed_kyc.py                # perfiles KYC base (Layer 2)
│   └── build_database.py          # construye risk_profiling.db
└── src/                           # MOTOR pKYC (lógica de riesgo, sin tocar APIs)
    ├── config.py                  # configuración desde .env
    ├── security/anonymizer.py     # proxy de enmascarado GDPR / secreto bancario
    ├── detectors/                 # Page-Hinkley, Z-Score transaccional, fusión Bonferroni
    ├── graph/contagion.py         # contagio topológico dirigido (NetworkX)
    ├── entities/resolver.py       # resolución de entidades (fuzz.ratio, anti-layering)
    ├── triage/ner.py              # triaje de relevancia local (Stage 1, sin coste)
    ├── llm/                       # agentes: Sentinel (Ollama) + AML-Synthesizer (Groq)
    ├── governance/workflow.py     # máquina de estados de doble autorización (four-eyes)
    ├── cost/tracker.py            # contabilidad de tokens y coste por 1000 análisis
    ├── ingestion/repository.py    # acceso de solo lectura a la base de datos
    ├── pipeline.py                # orquestador de las 6 fases
    ├── run_demo.py                # CLI demo single-client
    ├── run_scenario_demo.py       # replay de escenarios drift curados
    └── run_global_demo.py         # CLI demo multi-cliente (orquestador global)
```

---

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Infraestructura de inferencia

El motor usa inferencia **local** (coste cero, datos sensibles enmascarados) y
**en la nube** solo para el informe final de una alarma confirmada.

```bash
# Inferencia local (Ollama): extracción de hechos + embeddings semánticos
ollama pull qwen3:8b
ollama pull nomic-embed-text

# Inferencia en la nube (Groq) para el informe AML final (Stage 4)
# Configura la clave en .env (ver más abajo).
```

`.env` (raíz del proyecto):

```env
GROQ_API_KEY="gsk_..."
OLLAMA_HOST="http://localhost:11434"
OLLAMA_EXTRACTOR_MODEL="qwen3:8b"
OLLAMA_EMBEDDING_MODEL="nomic-embed-text"
GROQ_REPORT_MODEL="llama-3.3-70b-versatile"
TARGET_FWER=0.05
COMBINED_RISK_THRESHOLD=0.5
MAX_EVENTS_PER_RUN=6      # eventos máximos analizados por ejecución
USE_LLM_BURN_IN=false     # calibración semántica determinista por defecto
```

> Stack de inferencia local: `qwen3:8b` (extracción de hechos, conforme a la
> especificación) y `nomic-embed-text` (embeddings semánticos). El motor
> desactiva el modo "thinking" de qwen3 (`think=False`) para obtener JSON
> determinista y baja latencia, agrupa todas las llamadas por modelo para que
> cada uno se cargue una sola vez, y los mantiene residentes (`keep_alive`).
> Cualquier modelo de Ollama es configurable vía `.env`.
>
> **Calibración semántica.** El cold-start del detector Page-Hinkley se
> construye de forma determinista a partir del perfil de onboarding (solo
> embeddings, sin coste de chat). Como las distancias coseno viven en una
> escala comprimida, la corriente semántica usa multiplicadores más sensibles
> (`PH_SEMANTIC_DELTA_STD`, `PH_SEMANTIC_THRESHOLD_STD`) que las corrientes
> topológica y transaccional. Para usar titulares sintéticos generados por el
> LLM (mayor fidelidad a la especificación, una llamada extra), exporta
> `USE_LLM_BURN_IN=true`.

---

## Uso del motor pKYC

Primero genera la base de datos (capa de datos) y después ejecuta el motor:

```bash
# 1. Construir / poblar la base de datos (Layer 1 + Layer 2)
python -m scripts.build_database

# 2. Listar los clientes disponibles
python -m src.run_demo --list

# 3. Analizar un cliente (deriva semántica de modelo de negocio)
python -m src.run_demo --company "MicroStrategy" --max-events 7

# 4. Cliente sancionado (contagio topológico desde un director sancionado)
python -m src.run_demo --company "VTB"

# 5. Simular además una anomalía transaccional (dormancy break / layering)
python -m src.run_demo --company "Wirecard" --simulate-tx-anomaly

# 6. Salida JSON completa (para integración / UI)
python -m src.run_demo --company "OpenAI" --json
```

Cada ejecución produce: el perfil de cliente, el enmascarado de identidades,
la exposición por contagio topológico con sus contribuidores, las tres
corrientes estadísticas con sus umbrales, la decisión de alarma, el flujo de
gobernanza de doble autorización con su traza de auditoría, el coste estimado
y, si se supera el umbral, el informe AML redactado por el agente en la nube.

---

## Demos recomendadas (casos probados)

Los siete clientes del seed (`scripts/seed_kyc.py`) son **empresas reales** elegidas
por narrativa de riesgo. El motor en runtime **solo lee** `data/risk_profiling.db`;
las APIs externas se usan al construir la base (`python -m scripts.build_database`).

### Clientes disponibles

| Cliente | Grupo | Historia principal |
|---------|-------|-------------------|
| Wirecard AG | A | Fraude contable / colapso estructural |
| FTX Trading Ltd | A | Fraude crypto / quiebra |
| MicroStrategy Incorporated | A | **Semantic drift**: BI software → Bitcoin treasury |
| OpenAI | A | Escala / señales regulatorias |
| VTB Bank | B | Sanciones + topología (Kostin, Estado ruso) |
| Gazprombank | B | Sanciones + exposición energética (Gazprom) |
| Surgutneftegas | B | Petrolera rusa sancionada |

### Demo single-client (mejor narrativa por caso)

```bash
source .venv/bin/activate

# Shock / litigation detection sobre el snapshot OSINT actual
python -m src.run_demo --company "MicroStrategy" --max-events 7

# Sanciones + contagio topológico local (Kostin 1.0 desde el grafo)
python -m src.run_demo --company "VTB" --max-events 5

# Fraude estructural + opcional anomalía transaccional simulada
python -m src.run_demo --company "Wirecard" --max-events 5 --simulate-tx-anomaly

# Quiebra crypto (SBF, Caroline Ellison)
python -m src.run_demo --company "FTX" --max-events 5

# Salida JSON completa (integración / UI)
python -m src.run_demo --company "MicroStrategy" --json
```

**Qué mirar en stderr:** `[STREAMING EVENT]`, `[GRAPH MUTATION]`, `[EARLY STOP]`.

### Demo de drift gradual — MicroStrategy replay

La evaluación retrospectiva sobre la DB live detecta muchos **shocks** (FTX
bankruptcy, sanciones VTB, insolvencia Wirecard). Para enseñar la matemática de
**drift gradual** sin depender de lo que Google News devuelva hoy, usa el replay
curado de MicroStrategy:

```bash
python -m src.run_scenario_demo
```

Este escenario está en `data/scenarios/microstrategy_drift.json` y usa hitos
públicos reales con fecha y URL (SEC/Strategy/CNBC):

| Evento | Fecha | Señal |
|--------|-------|-------|
| E1 | 2020-07-28 | Capital allocation menciona activos digitales |
| E2 | 2020-08-11 | Bitcoin pasa a ser treasury reserve asset |
| E3 | 2020-12-11 | Deuda convertible para comprar Bitcoin |
| E4 | 2021-02-24 | Compra adicional >$1B, estrategia ya material |
| E5 | 2022-03-29 | Préstamo colateralizado con Bitcoin |
| E6 | 2022-08-02 | Impairment $917.8M y cambio CEO/Chairman |

Salida esperada:

```text
idx | date       | combined | stream alarms      | trigger
  1 | 2020-07-28 | 0.0000   | none               | FALSE
  2 | 2020-08-11 | 0.0320   | none               | FALSE
  3 | 2020-12-11 | 0.1867   | none               | FALSE
  4 | 2021-02-24 | 0.4674   | none               | FALSE
  5 | 2022-03-29 | 0.8317   | none               | TRUE
  6 | 2022-08-02 | 0.9026   | semantic,topology  | TRUE
```

**Mensaje clave para jurado técnico:** el evento 5 cruza el umbral con
`stream alarms = none`; no es un `if keyword in text`, sino acumulación de
estadísticos Page-Hinkley y fusión probabilística de señales débiles.

El runner escribe:

```text
data/scenario_microstrategy_drift_result.json
data/scenario_microstrategy_drift_result.csv
```

El notebook `notebooks/retro_lead_time_evaluation.ipynb` incluye dos gráficas
adicionales para este replay: curva de riesgo acumulado y componentes de
DriftFusion.

#### Batería completa de escenarios curados

Para evaluación / PowerPoint, ejecuta los 7 escenarios curados:

```bash
python -m src.run_scenario_demo --all
```

Genera:

```text
data/scenario_replay_summary.csv
data/scenario_replay_events.csv
data/scenario_replay_summary.json
```

Escenarios incluidos:

| Escenario | Cliente | Tipo |
|-----------|---------|------|
| `wirecard_drift` | Wirecard | Fraude contable gradual |
| `ftx_rapid_deterioration` | FTX | Deterioro rápido de liquidez/gobernanza |
| `microstrategy_drift` | MicroStrategy | Drift estratégico real |
| `openai_regulatory_drift` | OpenAI | Drift regulatorio/gobernanza |
| `vtb_sanctions_escalation` | VTB | Escalada de sanciones |
| `gazprombank_sanctions_escalation` | Gazprombank | Exposición energía/sanciones |
| `surgutneftegas_sanctions_escalation` | Surgutneftegas | Escalada sectorial petróleo/sanciones |

Resultado esperado tras `--all`: todos los escenarios tienen varios eventos
pre-alarma y congelan en evento 4 o 5, no en evento 1. Esto es lo que demuestra
memoria temporal y acumulación matemática.

### Demo global — orquestador multi-cliente

Simula varios clientes en **una cola temporal** con **memoria de amenazas compartida**
(`shared_threat_memory`). Cada cliente tiene su ego-graph aislado; el contagio cruzado
solo ocurre si **dos clientes comparten el mismo nombre de entidad** en su KYC.

```bash
source .venv/bin/activate
```

#### Demo estrella — cluster soberano ruso (contagio cruzado)

```bash
python -m src.run_global_demo --companies VTB Gazprombank --max-events 5
```

| Paso | Qué pasa |
|------|----------|
| Feb 2022, evento 1 | VTB congela (`risk≈0.85`, topology=1.0). Publica amenazas en memoria global. |
| Mar 2022, evento 2 | Gazprombank **hereda** `Government of Russia` (0.15 → 0.90) y congela (`risk≈0.84`). |

Log clave a señalar en pantalla:

```text
[GLOBAL ORCHESTRATOR] Cross-client threat inherited target=Gazprombank entity=Government of Russia risk=0.9000
[GLOBAL ORCHESTRATOR] Early stop target=Gazprombank risk=0.8386
```

**Frase para el pitch:** VTB procesa sanciones y publica riesgo soberano. Gazprombank
comparte esa exposición en su KYC (vínculo `ASSOCIATED_WITH`, peso bajo). En su primer
evento relevante, hereda la señal **antes** de evaluar su propia noticia.

#### Demo alternativa — inversor VC compartido

```bash
python -m src.run_global_demo --companies FTX OpenAI --max-events 5
```

| Paso | Qué pasa |
|------|----------|
| Nov 2022 | FTX congela en quiebra; publica `Sequoia Capital` (0.53). |
| Jun 2026 | OpenAI hereda Sequoia (0.20 → 0.53) y congela. Salto temporal 2022→2026. |

```text
[GLOBAL ORCHESTRATOR] Cross-client threat inherited target=OpenAI entity=Sequoia Capital risk=0.5330
```

Historía distinta al cluster ruso: contagio por **mismo inversor institucional** (Sequoia
invirtió en OpenAI y también en FTX).

#### Demo triple cluster (herencia sin alarma en el tercero)

```bash
python -m src.run_global_demo --companies VTB Gazprombank Surgutneftegas --max-events 5
```

- VTB y Gazprombank: ambos con alarma (igual que la demo estrella).
- Surgutneftegas **sí hereda** `Government of Russia` en 2025, pero sus noticias no
  pasan triage (no mencionan el nombre de la empresa) → no llega a alarma.
- Útil para explicar: la memoria global actualiza el grafo aunque el evento sea
  filtrado por relevancia.

#### Qué NO esperar (comportamiento correcto)

| Combinación | Resultado |
|-------------|-----------|
| VTB + MicroStrategy | Sin contagio cruzado: no comparten entidades en KYC. MicroStrategy cae por drift/fraude propio. |
| Kostin en MicroStrategy | **No hacerlo**: conexión artificial entre casos reales. |
| Surgutneftegas solo en global | Suele quedar sin alarma: titulares genéricos de “sanciones a Rusia” sin alias de la empresa. |

### Vínculos compartidos en el seed (contagio defendible)

Definidos en `scripts/seed_kyc.py` para habilitar herencia en el orquestador global:

| Entidad compartida | Clientes | Rol en KYC |
|--------------------|----------|------------|
| `Government of Russia` | VTB (accionista), Gazprombank, Surgutneftegas (nexus soberano) | Exposición jurisdiccional / estatal |
| `Gazprom` | VTB (contraparte energética), Gazprombank (accionista) | Cadena energía–banca |
| `Sequoia Capital` | FTX, OpenAI | Mismo inversor institucional |

Vínculos secundarios usan `rel_type: ASSOCIATED_WITH` con `control_weight: 0.1` y
`at_onboarding_risk` bajo (0.15–0.20): refleja lo que el banco sabía en onboarding,
no el screening OSINT completo.

### Por qué hace falta `at_onboarding_risk`

El collector de topología (`scripts/collectors/topology.py`) puede calcular riesgo
OSINT alto para una entidad (p. ej. `Government of Russia` = 0.6 en todos). La
herencia global solo dispara si `global_risk > local_risk`. Sin baseline de onboarding
más bajo en vínculos secundarios, **nunca** aparece `Cross-client threat inherited`.

Tras reconstruir la DB de clientes modificados:

```bash
python -m scripts.build_database --company VTB
python -m scripts.build_database --company Gazprombank
python -m scripts.build_database --company Surgutneftegas
python -m scripts.build_database --company OpenAI
```

### Reconstruir todo desde cero

```bash
source .venv/bin/activate
python -m scripts.build_database --reset
python -m src.run_global_demo --companies VTB Gazprombank --max-events 5
python -m src.run_demo --company "MicroStrategy" --max-events 7
```

### Logs stderr útiles (global)

| Log | Significado |
|-----|-------------|
| `[GLOBAL ORCHESTRATOR] Loaded N client pipelines` | Cola temporal montada |
| `Shared threat published source=… entity=…` | Cliente publica entidad con risk > 0.5 |
| `Cross-client threat inherited target=… entity=…` | **Contagio cruzado** — otro cliente hereda |
| `Early stop target=…` | Cliente congelado; eventos futuros ignorados |
| `skipped_client_frozen` | Simulación temporal: cliente ya cerrado |
| `skipped_by_triage` | Evento descartado sin LLM (sin mención al cliente/grafo) |

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docu/final_implementation.md`](docu/final_implementation.md) | Marco matemático, pipeline de agentes, esquemas JSON, código Python de referencia |
| [`docu/info_challenge.md`](docu/info_challenge.md) | Enunciado del reto, casos de uso y criterios de evaluación AMINA Bank |

> **Nota:** Las fórmulas LaTeX del documento técnico requieren preview con soporte matemático (`markdown.math.enabled: true` en VS Code/Cursor) o visualizarse en GitHub.

---

## Reto

**Dynamic Risk Profiling System (Real-Time Intelligence)** — SwissHacks 2026 / AMINA Bank Challenge.

Enfoque en eficiencia de costes (~95 % de eventos sin LLM), explicabilidad matemática auditable y gobernanza reguladora suiza (GDPR, four-eyes, audit trail).
