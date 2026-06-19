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

```
.
├── README.md
├── requirements.txt
├── docu/
│   ├── final_implementation.md   # Especificación técnica completa
│   └── info_challenge.md         # Descripción oficial del reto
└── scripts/
    └── api_tests/
        └── test_google_news.py
```

---

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependencias previstas del motor (ver spec):

```bash
pip install networkx numpy rapidfuzz
```

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
