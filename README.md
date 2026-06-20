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
    └── run_demo.py                # CLI de demostración
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
```

> Stack de inferencia local: `qwen3:8b` (extracción de hechos, conforme a la
> especificación) y `nomic-embed-text` (embeddings semánticos). El motor
> desactiva el modo "thinking" de qwen3 para obtener JSON determinista y baja
> latencia; cualquier modelo de Ollama es configurable vía `.env`.

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
