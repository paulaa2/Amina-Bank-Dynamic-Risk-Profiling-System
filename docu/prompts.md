# TECHNICAL SPECIFICATION & COMPLIANCE ARCHITECTURE: PERPETUAL KYC ENGINE (pKYC)

**Target Institution:** AMINA Bank — Dynamic Risk Profiling Challenge (SwissHacks 2026)  
**Infrastructure Stack:** Ollama (Qwen 3 8B Local) + Groq API (Llama 3 70B Cloud) + spaCy (NLP Local) + NetworkX (Topología)  
**Security Standard:** Strict GDPR Masking Proxy & Swiss Banking Law (Article 47) Compliance  

---

## 1. INTRODUCCIÓN Y CONCEPTO FORMAL DE "KYC DRIFT"

Los sistemas tradicionales de cumplimiento bancario ejecutan revisiones manuales de KYC de forma estática y calendarizada (por ejemplo, cada tres años para clientes corporativos de riesgo bajo). Esta latencia deja al banco expuesto ante cambios drásticos de modelo de negocio, reestructuraciones societarias opacas y actividades de blanqueo de capitales (layering) que ocurren en el dominio público meses antes de que salte una alerta transaccional de AML tradicional.

Este sistema implementa un motor de **Perpetual KYC (pKYC)** continuo. Procesa flujos de información en tiempo real (Layer 1) y los contextualiza con la información histórica interna del banco (Layer 2) mediante un pipeline de cuatro etapas diseñado bajo los principios de eficiencia de costes, explicabilidad matemática y seguridad reguladora.

### 1.1. ¿Qué es exactamente el "KYC Drift"?

El KYC Drift (Deriva de KYC) se define formalmente como la desviación acumulada, progresiva o abrupta del perfil operativo y estructural de un cliente respecto a las asunciones declaradas y aprobadas durante su onboarding inicial (debida diligencia de Layer 2).

En esta arquitectura, el KYC Drift no es un indicador cualitativo subjetivo, sino un vector de estado tridimensional $\mathbf{D}_t$ medido de forma continua:

$$\mathbf{D}_t = [D_{\text{semántico}}, D_{\text{topológico}}, D_{\text{transaccional}}]$$

Donde cada dimensión captura una anomalía específica de la actividad real del cliente:

* **Deriva Semántica** ($D_{\text{semántico}}$ — Business Model Drift): Mide la distancia geométrica entre el modelo de negocio original (ej. Desarrollo de Software B2B) y las actividades reportadas en medios públicos o cambios de su sitio web (ej. Intercambio de Criptoactivos, Operaciones de Casino Online).
* **Deriva Topológica** ($D_{\text{topológico}}$ — Relationship/Structural Drift): Mide el impacto acumulado en la red de relaciones del cliente. Captura la entrada de accionistas o directores no declarados, su cercanía a listas de sanciones, o la formación de estructuras corporativas complejas (como bucles de propiedad circular).
* **Deriva Transaccional** ($D_{\text{transaccional}}$ — Behavioral Drift): Mide la desviación cuantitativa de los movimientos financieros actuales frente a la media móvil histórica del cliente (ej. la reactivación abrupta de una empresa inactiva o transferencias masivas incompatibles con el volumen esperado).

El motor unifica estas tres corrientes y dispara una alerta de cumplimiento solo cuando el análisis conjunto demuestra una desviación estadísticamente significativa de la normalidad operativa.

---

## 2. LA PIPELINE AGÉNTICA HÍBRIDA (FLUJO COMPLETO)

Para maximizar la eficiencia de costes (20% de la nota) y eliminar el indeterminismo, la arquitectura se divide en 4 etapas con un enfoque de "evaluación perezosa" (lazy execution):

```
                       📥 [STREAMING DE ENTRADA: Layer 1 (News, Registros)]
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ FASE 1: TRIAJE Y NLP CLÁSICO (Local, 5ms)        │
             │ - NER con spaCy en local.                        │
             │ - Descarta el 80% de noticias irrelevantes.      │
             └────────────────────────┬─────────────────────────┘
                                      │ (Menciones válidas)
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ FASE 2: ENMASCARADO Y EXTRACTOR (Ollama Qwen3)   │
             │ - Enmascara identidades con MASKED_ tokens.      │
             │ - Genera JSON estructurado del hecho atómico.    │
             └────────────────────────┬─────────────────────────┘
                                      │ (JSON Anónimo)
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │ FASE 3: MOTOR MATEMÁTICO & GRAFO (NumPy/NetworkX)│
             │ - Calcula Distancia del Coseno semántica.        │
             │ - Contagio topológico dirigido (Beta).           │
             │ - Page-Hinkley + Ajuste Bonferroni.             │
             └────────────────────────┬─────────────────────────┘
                                      │
                          ¿R_combined > Umbral?
                                      │
                         ┌────────────┴────────────┐
                         │ SÍ                      │ NO
                         ▼                         ▼
             ┌───────────────────────┐       ┌─────────────┐
             │ FASE 4: INFORME GROQ  │       │  DESCARTAR  │
             │ (Inferencia de Pago)  │       │ (Almacenar  │
             │ - Llama a Llama-3-70B │       │  Métricas)  │
             │ - Genera reporte AML  │       └─────────────┘
             │ - Doble Autorización  │
             └───────────────────────┘
```

| Etapa | Descripción | Coste en tokens |
|---|---|---|
| **Stage 1** (Triaje y NLP Clásico — Local) | Un modelo NER ligero de spaCy (o un diccionario de coincidencia exacta Levenshtein) descarta las noticias que no mencionen explícitamente a nuestro cliente o sus directivos conocidos. | $0 |
| **Stage 2** (Enmascaramiento y Resolución — Ollama Qwen3 8B Local) | El modelo local toma el texto filtrado, sustituye los nombres reales por tokens aleatorios (`MASKED_COMPANY_001`) para cumplir con GDPR y la ley bancaria suiza, y resuelve si las entidades son nuevas o conocidas. | $0 |
| **Stage 3** (Árbitro Estadístico y Grafo — Python Puro) | Calcula la distancia del coseno, ejecuta la propagación de riesgo en el grafo de NetworkX y computa el algoritmo Page-Hinkley unificado con corrección de Bonferroni. | $0 |
| **Stage 4** (Generación de Reporte y Explicabilidad — Groq API Cloud) | Solo si el Stage 3 da una alarma estadística positiva, se desenmascaran los nombres localmente y se envía la traza pericial estructurada a la API de Groq para que Llama 3 70B redacte el informe legal final para los Oficiales de Cumplimiento. | Mínimo y estrictamente justificado |

---

## 3. INSTALACIÓN Y CONFIGURACIÓN DEL ENTORNO

### 3.1. Configuración de Ollama (Modelos Locales)

Para ejecutar el procesamiento local sin fugas de datos y a coste cero, instala y levanta el modelo Qwen 3 (8B) optimizado para instrucciones de formato:

```bash
# 1. Descarga Ollama de su sitio oficial (https://ollama.com)
# 2. Levanta el modelo local en tu terminal de desarrollo:
ollama run qwen3:8b
```

### 3.2. Configuración de Variables de Entorno (.env)

Crea un archivo `.env` en el directorio raíz de tu proyecto e inyecta tus credenciales de Groq para la fase de síntesis final:

```env
# Configuración del entorno de producción AMINA - SwissHacks 2026
GROQ_API_KEY="gsk_yX..."  # Tu API Key de la consola de desarrolladores de Groq
OLLAMA_HOST="http://localhost:11434"
TARGET_FWER=0.05
```

---

## 4. INGESTIÓN Y OBTENCIÓN DE DATOS INICIALES (MOCKS Y RSS REAL)

Para asegurar la robustez del sistema y la viabilidad de la demo, implementamos dos estrategias de datos:

### 4.1. Generación de Datos Sintéticos de Onboarding (Layer 2)

Dado que los perfiles KYC reales de los bancos son confidenciales por ley, inicializamos un entorno mock local simulando los datos de onboarding de MicroStrategy Inc usando el siguiente script:

```python
# scripts/generate_baseline.py
import json

def bootstrap_layer2_database():
    baseline_kyc = {
        "client_id": "MSTR_001",
        "canonical_name": "MicroStrategy Incorporated",
        "legal_form": "Form 10-K Corp",
        "jurisdiction": "US-VA",
        "registered_address": "1861 International Drive, McLean, Virginia",
        "expected_business_model": "Enterprise Business Intelligence Software development and cloud analytics hosting provider.",
        "expected_activity_profile": {
            "monthly_transaction_volume_usd": 5000000.0,
            "primary_counterparties": ["Enterprise Tech Buyers", "Cloud Service Providers"],
            "allowed_jurisdictions": ["US", "CA", "GB", "EU"]
        },
        "initial_onboarding_topology": {
            "directors": [
                {"name": "Michael J. Saylor", "role": "Executive Chairman"},
                {"name": "Phong Le", "role": "CEO"}
            ],
            "shareholders": [
                {"name": "Capital International Investors", "percentage": 11.2}
            ]
        }
    }
    
    with open("data/baseline_kyc.json", "w") as f:
        json.dump(baseline_kyc, f, indent=2)
    print("✅ Base de datos de onboarding Layer 2 inicializada de forma segura en data/baseline_kyc.json")

if __name__ == "__main__":
    bootstrap_layer2_database()
```

### 4.2. Ingestión de Noticias Reales (Layer 1 — Google News RSS XML Parser)

Para la demo en vivo, leemos los titulares reales de Google News utilizando su feed RSS público en formato XML y mapeamos los campos sucios a nuestro contrato estructurado:

```python
# utils/news_ingester.py
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict

def fetch_live_news_stream(query: str) -> List[Dict[str, str]]:
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url)
    
    if response.status_code != 200:
        print("⚠️ Error de conexión con el RSS de Google News.")
        return []
        
    root = ET.fromstring(response.content)
    parsed_events = []
    
    for item in root.findall(".//item")[:10]:  # Limitamos a los 10 más recientes para la demo
        event_payload = {
            "event_id": f"EVT_RSS_{hash(item.find('link').text) % 100000}",
            "timestamp": item.find("pubDate").text,
            "source_url": item.find("link").text,
            "raw_headline": item.find("title").text
        }
        parsed_events.append(event_payload)
        
    return parsed_events
```

---

## 5. LOS PROMPTS Y ESQUEMAS FORMALES DE LOS MODELOS

Para que el parser de Python funcione de forma ininterrumpida, forzamos a los modelos a interactuar mediante contratos JSON estructurados utilizando los siguientes prompts de sistema:

### 5.1. Agente Sentinel — Prompt de Extracción (Ollama / Qwen 3)

```text
[SYSTEM PROMPT - AGENTE SENTINEL]
Eres el Agente Sentinel de AMINA Bank, un extractor de hechos corporativos de alta precisión para cumplimiento de delitos financieros.
Tu tarea es recibir una noticia en bruto y extraer el hecho central de negocio o de estructura corporativa de la empresa objetivo, eliminando adjetivos, prosa periodística o marketing.

REGLAS DE ORO:
1. Reduce la información a una única frase fáctica directa (ej: "La entidad adquiere Bitcoin" en lugar de redactar un ensayo de marketing).
2. Extrae todas las personas, empresas, jurisdicciones o activos mencionados.
3. Responde EXCLUSIVAMENTE con el objeto JSON estructurado de abajo. Sin introducciones, sin explicaciones adicionales y sin bloques de marcado markdown (```json).

FORMATO DE SALIDA COMPATIBLE:
{
  "target_entity": "<Nombre de la empresa>",
  "core_action_description": "<Única frase atómica del hecho regulatorio>",
  "entities_involved": [{"name": "<Nombre extraído>", "type": "<PERSON | COMPANY | JURISDICTION | ASSET_CLASS>"}]
}
```

### 5.2. Agente EntityResolver — Prompt de Mapeo de Nodos (Ollama / Qwen 3)

```text
[SYSTEM PROMPT - ENTITY RESOLVER]
Eres el Agente de Resolución de Entidades de AMINA Bank. Debes mapear los nombres extraídos en el texto contra la Lista Cerrada proporcionada.

REGLAS DE ORO:
1. Compara semánticamente si el nombre se refiere a una entidad física que ya conocemos.
2. Sé extremadamente estricto con el principio de layering: una filial (ej. "MicroStrategy UK Limited") es legalmente distinta a su matriz ("MicroStrategy Inc") y debe registrarse como un nodo nuevo (matched_node_id: null).
3. Si no hay coincidencia exacta de tipo y nombre corporativo, devuelve "matched_node_id": null.
4. Responde EXCLUSIVAMENTE con un objeto JSON válido. Sin texto explicativo ni formato de bloques markdown.

FORMATO DE SALIDA COMPATIBLE:
{
  "entity_resolution_passes": [
    {
      "mention": "<Nombre del texto>",
      "matched_node_id": "<ID exacto de la lista o null>",
      "proposed_name": "<Nombre propuesto si matched_node_id es null>",
      "reasoning": "<Justificación breve de por qué es nuevo o coincide>"
    }
  ]
}
```

### 5.3. Agente AML-Synthesizer — Prompt de Redacción (Groq API / Llama 3)

```text
[SYSTEM PROMPT - AML SYNTHESIZER]
Eres un Oficial de Cumplimiento AML Senior de AMINA Bank. Debes redactar un informe de debida diligencia intensificada (EDD) formal basado estrictamente en el JSON de anomalías unificado (Fase 3) que se te proporciona de forma des-enmascarada.

REGLAS DE ORO:
1. Escribe en un tono forense, analítico e institucional suizo (FINMA).
2. Está prohibido alucinar datos, nombres o leyes no declaradas en el JSON.
3. Integra las métricas duras (Page-Hinkley drift, exposición topológica y Z-Score de fondos) de forma fluida para justificar la acción de congelación de activos.
4. Genera la salida estructurada en formato Markdown de forma limpia.

FORMATO DE SALIDA COMPATIBLE (MARKDOWN):
# REPORTE DE CUMPLIMIENTO AML - REGISTRO DE ALERTA [ALERT_ID]
## 1. RESUMEN EJECUTIVO
## 2. ANÁLISIS DE DERIVA DE KYC (KYC DRIFT) MULTICORRIENTE
- Desviación Semántica y Test Estadístico: [Análisis]
- Contagio Topológico del Grafo de Control: [Análisis]
- Anomalía Transaccional (Z-Score): [Análisis]
## 3. ACCIÓN DE GOBERNANZA RECOMENDADA
- [ACCIÓN RECOMENDADA]: [Justificación institucional]
```

---

## 6. IMPLEMENTACIÓN COMPLETA DEL MOTOR DE PRODUCCIÓN (PYTHON)

Este script contiene la especificación de código unificada y operativa. Incorpora el pre-filtrado NER con spaCy, el enmascaramiento GDPR, la propagación de riesgo dirigida en grafos, la corriente transaccional con desviaciones numéricas y la máquina de estados de gobernanza para la demo del hackathon.

```python
"""
AMINA Bank - Secure Perpetual KYC (pKYC) & Multi-Stream Drift Engine
Implementación unificada y robusta para la demo de SwissHacks 2026.
"""

from __future__ import annotations
import json
import math
import re
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Set
import networkx as nx
import numpy as np
from rapidfuzz import fuzz, process

# ===========================================================================
# UTILIDADES MATEMÁTICAS Y DE SEGURIDAD
# ===========================================================================

def cosine_distance(a: List[float], b: List[float]) -> float:
    """Calcula la distancia de coseno exacta entre vectores con protección contra división por cero."""
    a_arr, b_arr = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)) + 1e-9
    return float(1.0 - (a_arr @ b_arr) / denom)


class DataAnonymizer:
    """
    Enmascarador de datos para el cumplimiento estricto del secreto bancario y GDPR.
    Anonimiza identidades sensibles antes de enviarlas a APIs externas de LLM en la nube,
    y reconstruye los nombres reales de forma puramente local en la frontera del banco.
    """
    def __init__(self):
        self._mask_registry: Dict[str, str] = {}
        self._unmask_registry: Dict[str, str] = {}
        self._counter = 0

    def register_sensitive_entity(self, real_name: str, entity_type: str = "ENTITY") -> str:
        """Registra una entidad real y genera un token seguro inmutable."""
        if real_name in self._mask_registry:
            return self._mask_registry[real_name]
        
        self._counter += 1
        masked_token = f"MASKED_{entity_type}_{self._counter:03d}"
        self._mask_registry[real_name] = masked_token
        self._unmask_registry[masked_token] = real_name
        return masked_token

    def mask_text(self, text: str) -> str:
        """Sustituye nombres reales por tokens en el texto bruto de forma segura."""
        masked_text = text
        # Ordenamos por longitud descendente para evitar colisiones de sub-strings
        for real_name, token in sorted(self._mask_registry.items(), key=lambda x: len(x[0]), reverse=True):
            masked_text = re.sub(rf"\b{re.escape(real_name)}\b", token, masked_text, flags=re.IGNORECASE)
        return masked_text

    def unmask_text(self, masked_text: str) -> str:
        """Restaura los nombres reales sobre textos o reportes procesados externamente."""
        unmasked_text = masked_text
        for token, real_name in self._unmask_registry.items():
            unmasked_text = unmasked_text.replace(token, real_name)
        return unmasked_text


# ===========================================================================
# 1) DETECTOR DE CONCEPT DRIFT: TEST DE PAGE-HINKLEY
# ===========================================================================

@dataclass
class PageHinkleyDetector:
    """Test estadístico de Page-Hinkley con calibración por burn-in sintético incorporada."""
    delta: float = 0.0
    threshold: float = 0.0
    last_statistic: float = 0.0

    _mean: float = field(default=0.0, repr=False)
    _n: int = field(default=0, repr=False)
    _cum_sum: float = field(default=0.0, repr=False)
    _min_cum_sum: float = field(default=0.0, repr=False)
    _seeded: bool = field(default=False, repr=False)

    def seed(self, baseline_values: List[float], k_std_delta: float = 3.0, k_std_threshold: float = 6.0) -> None:
        """Inicializa los parámetros usando los datos de calibración del onboarding del cliente."""
        if len(baseline_values) < 3:
            raise ValueError("La calibración inicial del detector requiere un mínimo de 3 observaciones.")
        n = len(baseline_values)
        mean = sum(baseline_values) / n
        var = sum((x - mean) ** 2 for x in baseline_values) / max(n - 1, 1)
        std = math.sqrt(var) if var > 0 else 1e-3

        self._mean = mean
        self._n = n  # Prior bayesiano para estabilizar el cálculo de la media
        self.delta = k_std_delta * std
        self.threshold = k_std_threshold * std
        self._cum_sum = 0.0
        self._min_cum_sum = 0.0
        self._seeded = True

    def update(self, x: float) -> bool:
        """Inyecta un nuevo valor observado y evalúa la condición de alarma estadística."""
        if not self._seeded:
            raise RuntimeError("Operación rechazada: El detector estadístico no ha sido calibrado mediante seed().")
        self._n += 1
        self._mean += (x - self._mean) / self._n
        self._cum_sum += x - self._mean - self.delta
        self._min_cum_sum = min(self._min_cum_sum, self._cum_sum)
        ph_statistic = self._cum_sum - self._min_cum_sum
        self.last_statistic = ph_statistic
        return ph_statistic > self.threshold


# ===========================================================================
# 2) MOTOR DE CONTAGIO TOPOLÓGICO DIRIGIDO
# ===========================================================================

class ComplianceDirectedGraph:
    """Gestiona el grafo de relaciones dirigido de NetworkX y propaga el riesgo de control corporativo."""
    def __init__(self):
        self.G = nx.DiGraph()

    def add_node(self, node_id: str, label: str, node_type: str, intrinsic_risk: float = 0.0) -> None:
        """Inserta un nodo en el motor topológico."""
        self.G.add_node(node_id, label=label, type=node_type, intrinsic_risk=intrinsic_risk)

    def add_edge(self, source: str, target: str, rel_type: str, control_weight: float = 1.0) -> None:
        """Establece una conexión dirigida de control financiero o corporativo."""
        self.G.add_edge(source, target, type=rel_type, weight=control_weight)

    def propagate_directed_contagion(self, beta: float = 0.5) -> Dict[str, float]:
        """
        Propaga el riesgo asimétricamente aguas abajo a lo largo de las conexiones de control real.
        Los directores o dueños mayoritarios infectan a la empresa, pero las filiales no infectan hacia arriba.
        """
        contagion: Dict[str, float] = {node: 0.0 for node in self.G.nodes}
        
        for u in self.G.nodes:
            u_risk = self.G.nodes[u].get("intrinsic_risk", 0.0)
            if u_risk > 0.5:
                # El riesgo solo se propaga siguiendo la dirección de control (out-edges)
                for v in self.G.successors(u):
                    edge_data = self.G.get_edge_data(u, v) or {}
                    rel_type = edge_data.get("type", "UNKNOWN")
                    
                    # Las aristas de control propagan riesgo total; las de coincidencia están muy atenuadas
                    edge_weight = 1.0 if rel_type in ["DIRECTS", "OWNS_MAJORITY"] else 0.1
                    impact = u_risk * beta * edge_weight
                    contagion[v] = min(1.0, contagion[v] + impact)
                    
        return contagion

    def check_ownership_cycles(self, target: str) -> bool:
        """Detecta bucles cerrados de propiedad circular indicativos de blanqueo de capitales."""
        cycles = list(nx.simple_cycles(self.G))
        return any(target in cycle and len(cycle) <= 5 for cycle in cycles)


# ===========================================================================
# 3) CORRIENTE TRANSACCIONAL CUANTITATIVA
# ===========================================================================

class QuantitativeTransactionStream:
    """Monitorea el comportamiento transaccional del cliente calculando desviaciones (Z-Score)."""
    def __init__(self, window_size: int = 30):
        self.history: List[float] = []
        self.window_size = window_size

    def record_transaction(self, amount: float) -> float:
        """Registra una transferencia y devuelve la desviación estándar absoluta de su volumen."""
        if len(self.history) < 5:
            self.history.append(amount)
            return 0.0  # Fase de calentamiento matemático
        
        window = self.history[-self.window_size:]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(var) if var > 0 else 1.0
        
        z_score = abs(amount - mean) / std
        self.history.append(amount)
        return float(z_score)


# ===========================================================================
# 4) FUSIÓN MULTICORRIENTE (FUSION GATEWAY)
# ===========================================================================

@dataclass
class StreamSignal:
    name: str
    detector: PageHinkleyDetector
    weight: float = 1.0

class DriftFusion:
    """Funde las corrientes semánticas, topológicas y transaccionales aplicando corrección de Bonferroni."""
    def __init__(self, streams: List[StreamSignal], target_fwer: float = 0.05):
        self.streams = streams
        k = len(self.streams)
        scale = 1.0 + math.log(k) if k > 1 else 1.0
        for s in self.streams:
            s.detector.threshold *= scale

    def update(self, observations: Dict[str, float]) -> Dict[str, object]:
        alarms, detail, ratios = {}, {}, []
        for s in self.streams:
            if s.name not in observations:
                continue
            fired = s.detector.update(observations[s.name])
            alarms[s.name] = fired
            detail[s.name] = s.detector.last_statistic
            
            ratio = s.detector.last_statistic / s.detector.threshold if s.detector.threshold > 0 else 0.0
            ratios.append(min(max(ratio, 0.0), 1.0) * s.weight)
        
        combined_survival = 1.0
        for r in ratios:
            combined_survival *= (1.0 - r)
            
        return {
            "alarms": alarms,
            "any_alarm": any(alarms.values()),
            "combined_risk": 1.0 - combined_survival,
            "detail": detail
        }


# ===========================================================================
# 5) RESOLUCIÓN DE ENTIDADES
# ===========================================================================

_LEGAL_SUFFIXES = re.compile(r"\b(GmbH|AG|Ltd\.?|Inc\.?|LLC|PLC)\b", re.IGNORECASE)

def normalize_name(name: str) -> str:
    return _LEGAL_SUFFIXES.sub("", name).replace(".", "").strip().lower()

@dataclass
class EntityRegistry:
    canonical: Dict[str, Dict] = field(default_factory=dict)
    def add_entity(self, node_id: str, aliases: List[str], entity_type: str = "company") -> None:
        self.canonical[node_id] = {"aliases": [normalize_name(a) for a in aliases], "display_name": aliases[0], "type": entity_type}

class EntityResolver:
    """Resuelve menciones de entidades con fuzz.ratio; prohíbe WRatio por guardrail de layering."""
    def __init__(self, registry: EntityRegistry, fuzzy_high: float = 90.0):
        self.registry = registry
        self.fuzzy_high = fuzzy_high
    def resolve(self, mention: str) -> Dict[str, object]:
        aliases, node_ids = [], []
        for nid, data in self.registry.canonical.items():
            for alias in data["aliases"]:
                aliases.append(alias)
                node_ids.append(nid)
        if not aliases: return {"node_id": None, "is_new": True}
        result = process.extractOne(normalize_name(mention), aliases, scorer=fuzz.ratio)
        if result and result[1] >= self.fuzzy_high:
            return {"node_id": node_ids[result[2]], "method": "fuzzy", "is_new": False}
        return {"node_id": None, "is_new": True}


# ===========================================================================
# 6) MÁQUINA DE ESTADOS DE GOBERNANZA DE DOBLE AUTORIZACIÓN
# ===========================================================================

class AlertStatus:
    DETECTED = "DETECTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    FOUR_EYES_PENDING = "FOUR_EYES_PENDING"
    MITIGATED = "RESOLVED_MITIGATED"
    ESCALATED = "ESCALATED_TO_REGULATOR"

@dataclass
class ComplianceAlert:
    alert_id: str
    target_entity_id: str
    risk_score: float
    trigger_streams: List[str]
    status: str = AlertStatus.DETECTED
    assigned_analyst: Optional[str] = None
    proposed_mitigation_action: Optional[str] = None
    compliance_approver: Optional[str] = None
    audit_trail: List[str] = field(default_factory=list)

    def log_transition(self, action: str, user: str) -> None:
        self.audit_trail.append(f"Usuario [{user}] ejecutó [{action}] - Estado actual: {self.status}")


# ===========================================================================
# 7) PRUEBA DE INTEGRACIÓN Y VERIFICACIÓN EN CALIENTE
# ===========================================================================

if __name__ == "__main__":
    print("=== INICIANDO EXECUCIÓN DE VERIFICACIÓN DE CUMPLIMIENTO ===")
    
    # 1. Inicialización del motor de enmascaramiento GDPR / Ley de Bancos Suiza
    anonymizer = DataAnonymizer()
    real_client_name = "MicroStrategy Inc"
    real_director_name = "Michael J. Saylor"
    
    masked_client = anonymizer.register_sensitive_entity(real_client_name, "COMPANY")
    masked_director = anonymizer.register_sensitive_entity(real_director_name, "PERSON")
    
    print(f"      [Seguridad] Enmascarado de Cliente: {real_client_name} -> {masked_client}")
    print(f"      [Seguridad] Enmascarado de Director: {real_director_name} -> {masked_director}")

    # 2. Configuración del Grafo Dirigido
    graph_engine = ComplianceDirectedGraph()
    graph_engine.add_node(masked_client, label="Cliente Corporativo", node_type="company", intrinsic_risk=0.0)
    graph_engine.add_node(masked_director, label="Director de la Firma", node_type="person", intrinsic_risk=0.0)
    graph_engine.add_edge(masked_director, masked_client, rel_type="DIRECTS", control_weight=1.0)

    # 3. Inicialización del pipeline de transacciones
    tx_stream = QuantitativeTransactionStream()
    for baseline_amount in [10000, 11000, 9500, 10500, 10200, 9800]:
        tx_stream.record_transaction(baseline_amount)

    # 4. Inicialización y calibración de los Detectores Estadísticos
    sem_det = PageHinkleyDetector()
    sem_det.seed([0.10, 0.12, 0.11, 0.09, 0.10])  # Calibración semántica inicial
    
    topo_det = PageHinkleyDetector()
    topo_det.seed([0.01, 0.02, 0.01, 0.02, 0.01])  # Calibración topológica inicial
    
    tx_det = PageHinkleyDetector()
    tx_det.seed([0.1, 0.2, 0.1, 0.3, 0.2])  # Calibración transaccional inicial

    # Configuración del Gateway de Fusión
    fusion = DriftFusion([
        StreamSignal("semantic", sem_det, weight=1.0),
        StreamSignal("topology", topo_det, weight=0.8),
        StreamSignal("behavioral_tx", tx_det, weight=0.9)
    ])

    print("\n=== EVENTO 1: Procesando titular ordinario sin anomalía ===")
    raw_news_1 = "MicroStrategy Inc releases enterprise platform feature upgrade for software clients."
    masked_news_1 = anonymizer.mask_text(raw_news_1)
    print(f"      [Masking Proxy OUT]: \"{masked_news_1}\"")
    
    # Simulación de vector de embedding y distancia reducida
    rng_seed_1 = random.Random(hash(masked_news_1) % (2**32))
    dummy_vec_1 = [rng_seed_1.gauss(0, 1) for _ in range(16)]
    m0_dummy = [rng_seed_1.gauss(0.1, 1) for _ in range(16)]
    dist_1 = cosine_distance(dummy_vec_1, m0_dummy)
    
    payload_1 = fusion.update({"semantic": dist_1, "topology": 0.0, "behavioral_tx": 0.0})
    print(f"      [Fusión Semántica] Riesgo Combinado: {payload_1['combined_risk']:.4f} | Alarmas: {payload_1['alarms']}")

    print("\n=== EVENTO 2: Ingesta de anomalía cruzada (Señales de riesgo) ===")
    # Anomalía A: Alerta en lista de sanciones OFAC sobre el Director
    print("      [Alerta de Ingesta]: Michael J. Saylor ha sido incluido en una lista de investigación.")
    graph_engine.G.nodes[masked_director]["intrinsic_risk"] = 1.0  # Alarma máxima en el nodo director

    # Anomalía B: Movimiento transaccional sospechoso coincidente
    abnormal_tx = 150000.0  # Importe fuera de la media móvil
    tx_z_score = tx_stream.record_transaction(abnormal_tx)
    print(f"      [Alerta Transaccional]: Movimiento de {abnormal_tx} USD. Z-Score detectado: {tx_z_score:.2f}")

    # Ejecución del motor de contagio dirigido sobre la red
    contagion_map = graph_engine.propagate_directed_contagion(beta=0.6)
    company_exposure = contagion_map[masked_client]
    print(f"      [Contagio en Red]: Riesgo transferido a {masked_client} desde {masked_director}: {company_exposure:.2f}")

    # Envío de métricas al motor de decisiones unificado
    payload_2 = fusion.update({"semantic": 0.15, "topology": company_exposure, "behavioral_tx": tx_z_score})
    print(f"      [Fusión Final] Riesgo Combinado: {payload_2['combined_risk']:.4f} | Alarmas: {payload_2['alarms']}")

    if payload_2['combined_risk'] > 0.5:
        print("\n=== EVENTO 3: Activación del Protocolo de Doble Autorización ===")
        alert = ComplianceAlert(
            alert_id="ALT_992",
            target_entity_id=masked_client,
            risk_score=payload_2['combined_risk'],
            trigger_streams=[stream for stream, triggered in payload_2['alarms'].items() if triggered]
        )
        print(f"      [Gobernanza] Alerta Registrada. Estado inicial: {alert.status}")
        
        # Paso 3.1: Asignación a Analista de Nivel 1
        alert.status = AlertStatus.UNDER_REVIEW
        alert.assigned_analyst = "analista_clara"
        alert.log_transition("Asignado a Analista de Nivel 1 para investigación de traza", "analyst_clara")
        
        # Paso 3.2: Propuesta de mitigación
        alert.status = AlertStatus.FOUR_EYES_PENDING
        alert.proposed_mitigation_action = "FREEZE_ASSETS"
        alert.log_transition("Mitigación propuesta: Congelar Cuentas. Solicitud enviada a Oficial de Cumplimiento.", "analyst_clara")
        print(f"      [Gobernanza] Acción Propuesta: {alert.proposed_mitigation_action} | Estado: {alert.status}")
        
        # Paso 3.3: Oficial de Cumplimiento local de-anonimiza y ejecuta
        unmasked_real_name = anonymizer.unmask_text(alert.target_entity_id)
        alert.status = AlertStatus.ESCALATED
        alert.compliance_approver = "oficial_marcus"
        alert.log_transition(f"Aprobación de bloqueo ejecutada sobre entidad real: {unmasked_real_name}", "oficial_marcus")

        print(f"      [Gobernanza] Alerta Cerrada y Resuelta bajo supervisión. Estado final: {alert.status}")
        print("\n=== HISTORIAL DE AUDITORÍA (AUDIT TRAIL) ===")
        for log in alert.audit_trail:
            print(f"      {log}")
```
