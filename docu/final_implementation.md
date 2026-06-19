# ESPECIFICACIÓN TÉCNICA DE ARQUITECTURA: MOTOR pKYC REFORZADO

**Cliente Objetivo:** AMINA Bank — Reto de Perfilado de Riesgo Dinámico (SwissHacks 2026)  
**Metodología:** Detección Estadística de Concept Drift (Page-Hinkley) + Contagio de Riesgo Topológico Dirigido + Enmascaramiento GDPR + Gobernanza de Doble Autorización  
**Documento de Ingeniería:** Guía Completa de Desarrollo e Integración  

---

## 1. INTRODUCCIÓN Y CONCEPTO FORMAL DE "KYC DRIFT"

Los sistemas tradicionales de cumplimiento bancario ejecutan revisiones manuales de KYC de forma estática y calendarizada (por ejemplo, cada tres años para clientes corporativos de riesgo bajo). Esta latencia deja al banco expuesto ante cambios drásticos de modelo de negocio, reestructuraciones societarias opacas y actividades de blanqueo de capitales (layering) que ocurren en el dominio público meses antes de que salte una alerta transaccional de AML tradicional.

Este sistema implementa un motor de **Perpetual KYC (pKYC)** continuo. Procesa flujos de información en tiempo real (Layer 1) y los contextualiza con la información histórica interna del banco (Layer 2) mediante un pipeline diseñado bajo los principios de eficiencia de costes, explicabilidad matemática y seguridad reguladora.

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

## 2. MARCO MATEMÁTICO DE DECISIÓN

### 2.1. Distancia Semántica de Eventos (Layer 2 vs Layer 1)

En el onboarding del cliente se genera un perfil base inmutable $P_{\text{base}}$ con datos internos. Este perfil se convierte en un vector de referencia estático $m_0$:

$$m_0 = \text{Embed}(P_{\text{base}}) \in \mathbb{R}^{d}$$

Cada evento público entrante $E_t$ es filtrado de ruido y convertido en un vector temporal $e_t \in \mathbb{R}^{d}$ mediante el mismo modelo de embeddings. La distancia semántica bruta se calcula mediante la Distancia del Coseno:

$$D_C(m_0, e_t) = 1 - \frac{m_0 \cdot e_t}{\|m_0\| \|e_t\|}$$

### 2.2. Algoritmo de Detección de Drift de Page-Hinkley

El stream de distancias semánticas se introduce en el test de Page-Hinkley. Para cada observación $x_t = D_C(m_0, e_t)$ en el instante $t$:

1. **Actualización de la Media Running:**
   $$\mu_t = \mu_{t-1} + \frac{x_t - \mu_{t-1}}{n_t}$$
   Donde $n_t$ es el número de observaciones acumuladas.

2. **Acumulador CUSUM de Desviación:**
   $$S_t = S_{t-1} + (x_t - \mu_t - \delta)$$
   Donde el parámetro de tolerancia $\delta$ representa la varianza semántica normalizada que el banco está dispuesto a tolerar como ruido operativo normal sin alterar el perfil de riesgo.

3. **Aislamiento de la Métrica de Cambio:**
   $$T_t = S_t - \min_{1 \leq i \leq t} (S_i)$$

4. **Condición de Alarma:**
   $$\text{Alarma}_t = \begin{cases} \text{True} & \text{si } T_t > \lambda \\ \text{False} & \text{si } T_t \leq \lambda \end{cases}$$
   Donde $\lambda$ es el umbral de alarma ajustado estadísticamente.

### 2.3. Contagio de Riesgo Topológico Dirigido y Ponderado

Definimos la propagación de riesgo de forma asimétrica dirigida. La exposición al riesgo de un nodo limpio $u$ se actualiza como:

$$\text{Exposición}_{u} = \min \left(1.0, \text{Exposición}_{u} + \sum_{v \in \mathcal{N}(u)} (\text{Riesgo}_{v} \cdot \beta \cdot W_{vu})\right)$$

* $\mathcal{N}(u)$ son los vecinos directos (1 salto de distancia) que influyen sobre el nodo $u$.
* $\beta \in [0, 1]$ es el factor de atenuación de contagio (por defecto: `0.5`).
* $W_{vu}$ es el peso de control específico de la relación:
  * $W = 1.0$ para relaciones directas de control ejecutivo y propiedad mayoritaria: `DIRECTS`, `OWNS_MAJORITY` ($\geq 25\%$).
  * $W = 0.1$ para relaciones de coincidencia o propiedad minoritaria asociativa: `LOCATED_AT`, `OWNS_MINORITY` ($< 25\%$).

### 2.4. Fusión de Señales Multicorriente con Corrección de Bonferroni

El sistema procesa $k$ corrientes estadísticas paralelas de riesgo para un mismo cliente:

* **Corriente Semántica** ($T_{\text{semantic}}$): Desviación conceptual del modelo de negocio y noticias.
* **Corriente Topológica** ($T_{\text{topology}}$): Elevación de la exposición por contagio estructural y centralidad de conexiones.
* **Corriente Transaccional** ($T_{\text{transaction}}$): Anomalías cuantitativas en los flujos de fondos (Z-Score sobre importes y frecuencias de transferencias).

Para garantizar un objetivo de tasa de error familiar conjunto (FWER) controlado (ej. $\alpha = 0.05$), corregimos dinámicamente los umbrales individuales de Page-Hinkley mediante una aproximación logarítmica de Bonferroni:

$$\lambda_{\text{adjusted}, i} = \lambda_{\text{base}, i} \cdot (1 + \ln(k))$$

Para unificar estas tres corrientes en una única métrica continua para la bandeja del analista, aplicamos una fusión probabilística basada en la teoría de fallo de componentes independientes:

$$R_{\text{combined}} = 1 - \prod_{i=1}^{k} \left(1 - \min\left(1.0, \frac{T_{i, t}}{\lambda_{\text{adjusted}, i}}\right)\right)$$

---

## 3. ESQUEMAS DE DATOS DE INTEGRACIÓN

Para asegurar la reproducibilidad de la demo, se definen los formatos JSON de las capas del sistema.

### 3.1. Layer 2: Onboarding de Perfil Interno de Referencia (`baseline_kyc.json`)

```json
{
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
```

### 3.2. Layer 1: Estructura del Payload del Evento de Entrada Semántico

```json
{
  "event_id": "EVT_2026_099",
  "timestamp": "2026-06-20T01:15:00Z",
  "source_url": "https://www.bloomberg.com/news/articles/mstr-bitcoin",
  "extracted_facts": {
    "target_entity": "MicroStrategy Inc",
    "core_action_description": "MicroStrategy Incorporated shifts corporate balance sheet assets, liquidating cash reserves to buy 21000 Bitcoin.",
    "entities_involved": [
      {"name": "Michael J. Saylor", "type": "PERSON"},
      {"name": "Bitcoin", "type": "ASSET_CLASS"}
    ]
  }
}
```

---

## 4. LA PIPELINE DE AGENTES DE IA (ARQUITECTURA DE PROMPTS Y ROLES)

La pipeline utiliza tres agentes especializados para procesar, filtrar y resumir la información de manera estructurada y determinista.

```
[Noticia en Bruto / Registro]
              |
              v
     +-----------------+
     |  AGENTE 1:      |  -> Extrae hechos atómicos sin ruido publicitario.
     |  Sentinel       |     Genera entrada limpia para el vector semántico.
     +-----------------+
              |
              v
     +-----------------+
     |  AGENTE 2:      |  -> Resuelve ambigüedades contra la lista cerrada
     |  EntityResolver |     de IDs del grafo. Evita nodos duplicados.
     +-----------------+
              |
              v
     [Filtros Estadísticos / Contagio de Grafo local] (Sin coste de LLM)
              |
         (Brecha de Umbral)
              |
              v
     +-----------------+
     |  AGENTE 3:      |  -> Compila el informe final con los datos de-anonimizados.
     |  AML-Synthesizer|     Genera el reporte de doble autorización.
     +-----------------+
```

### Agente 1: Sentinel Fact-Extractor (Limpieza Semántica)

**Objetivo:** Eliminar el ruido periodístico y publicitario de las noticias brutas de Layer 1. Generar un resumen fáctico atómico para que el vector de embedding represente el cambio de negocio real y no la prosa del periodista.

**System Prompt:**

```text
Eres el Agente Sentinel de AMINA Bank, un extractor de hechos corporativos de alta precisión para cumplimiento de delitos financieros.
Tu única tarea es recibir un texto periodístico o actualización de registro y extraer EXCLUSIVAMENTE el hecho principal relacionado con la actividad de negocio o estructura corporativa de la empresa objetivo.

REGLAS DE ORO:
1. Elimina todo el ruido publicitario, opiniones, caídas de bolsa o menciones a competidores ajenos.
2. Reduce la información a una frase atómica e informativa (ej: "La empresa opera una casa de cambio criptográfica en el extranjero" en lugar de redactar un ensayo).
3. Responde estrictamente con la estructura JSON definida. No añadas introducciones, explicaciones ni bloques de código formateados.

Estructura de salida requerida:
{
  "target_entity": "<Nombre normalizado de la empresa objetivo>",
  "core_action_description": "<Hecho atómico extraído en una única frase clara>",
  "entities_involved": [{"name": "<Nombre>", "type": "<PERSON | COMPANY | JURISDICTION | ASSET_CLASS>"}]
}
```

### Agente 2: EntityResolver (Resolución de Entidades en Zona Ambigua)

**Objetivo:** Resolver nombres de directores, accionistas o subsidiarias complejos que caen en la zona gris (coincidencia parcial). Fuerza al LLM a elegir sobre una lista cerrada de IDs existentes en el grafo, evitando la duplicación de nodos y alucinaciones.

**System Prompt:**

```text
Eres el Agente de Resolución de Entidades de AMINA Bank. Tu misión es mapear menciones de nombres de personas u organizaciones extraídas del texto a nodos ya existentes dentro de nuestra base de datos relacional de cumplimiento.

Se te proporcionará:
1. Una mención que resolver (ej: "Michael Saylor").
2. El contexto de la noticia.
3. Una LISTA CERRADA de entidades ya conocidas en el grafo con sus IDs correspondientes.

REGLAS DE ORO:
1. Compara semántica y contextualmente si la mención se refiere de manera inequívoca a alguno de los IDs conocidos de la lista.
2. Si existe un nivel de sospecha o certeza de que se trata de la misma entidad física, devuelve el ID exacto.
3. Si la entidad no tiene ninguna relación lógica con los elementos de la lista, debes considerarla como una entidad nueva devolviendo "matched_node_id": null.
4. Responde ÚNICAMENTE con un objeto JSON sin formateadores externos ni explicaciones.

Formato de salida requerido:
{
  "matched_node_id": "<ID exacto de la lista proporcionada o null si es una nueva entidad>",
  "confidence": <float entre 0.0 y 1.0 indicando tu nivel de certeza lógica>,
  "proposed_name": "<Sugerencia de nombre de visualización solo si matched_node_id es null>"
}
```

### Agente 3: AML-Synthesizer (Redacción de Informes de Cumplimiento)

**Objetivo:** Generar la justificación de alarma para el flujo de doble autorización. Recibe la traza de anomalías (métrica de drift y saltos topológicos) tras haber sido desenmascarada por el proxy local (sustituyendo los tokens por los nombres reales) y redacta la recomendación del analista.

**System Prompt:**

```text
Eres un Oficial de Cumplimiento AML Senior de AMINA Bank. Tu tarea es compilar el reporte final de debida diligencia intensificada (EDD) para que el Oficial Principal autorice o rechace la mitigación propuesta.

Recibirás un JSON estructurado que contiene:
1. El perfil base de la empresa cliente registrado en su onboarding (Layer 2).
2. El hecho atómico (Noticia o Cambio) que ha disparado la alarma (Fase 1).
3. Las métricas matemáticas que han violado la barrera de normalidad (Page-Hinkley, Contagio de Grafo y Anomalía Transaccional).
4. El plan de acción preventivo sugerido por el analista de nivel 1.

REGLAS DE ORO:
1. Escribe en un tono formal, pericial y extremadamente estructurado.
2. Justifica detalladamente por qué la desviación detectada (Drift de KYC) invalida las asunciones del onboarding de la empresa.
3. Cita explícitamente las métricas matemáticas (ej: "Exposición al riesgo de la firma ascendió a 0.60 por contagio directo del director sancionado").
4. Genera una conclusión auditable para el Oficial de Cumplimiento suizo (FINMA).

Escribe el reporte en español técnico con la siguiente estructura:
# REPORTE DE CUMPLIMIENTO AML - REGISTRO DE ALERTA [ID_ALERTA]
## 1. RESUMEN EJECUTIVO
## 2. ANÁLISIS DE DERIVA DE KYC (KYC DRIFT ANALYSIS)
- Desviación Semántica: [Detalle del cambio de modelo de negocio]
- Impacto en Red Corporativa: [Detalle del contagio topológico por directores o dueños]
- Comportamiento Transaccional: [Desviación cuantitativa observada]
## 3. TRAZA DE MÉTRICAS AUDITABLES
- Concept Drift (Page-Hinkley): [Estadístico actual vs Umbral]
- Contagio Topológico Dirigido: [Grado de exposición]
- Z-Score de Fondos: [Z-Score transaccional]
## 4. PLAN DE ACCIÓN RECOMENDADO
```

---

## 5. ARQUITECTURA DEL PIPELINE DE CODIFICACIÓN (SISTEMA INTEGRADO)

El pipeline de ejecución se divide en seis fases modulares:

```
[Entrada de Texto Ingestada: Layer 1]
                 |
                 v
   [FASE 1: Proxy de Enmascaramiento] -> Reemplaza nombres reales por tokens aleatorios
                 |
                 v
   [FASE 2: Resolución de Entidades] -> Comprobación determinista (fuzz.ratio) e inserción
                 |
                 +-----------------------+-----------------------+
                 |                                               |
                 v                                               v
     [FASE 3.1: Filtro Semántico]                  [FASE 3.2: Motor de Grafo]
     - Extracción limpia con LLM                   - NetworkX Directed Graph
     - Embedding y Distancia de Coseno             - Contagio de Riesgo Dirigido (Beta)
     - Page-Hinkley de Distancia Semántica         - Análisis de Centralidad y Bucles
                 |                                               |
                 +-----------------------+-----------------------+
                                         |
                                         v
                             [FASE 4: Fusión de Riesgos]
                             - Corrección de Bonferroni Multicorriente
                             - Combinación Probabilística de Riesgo
                                         |
                            (Si Riesgo Fusionado > Umbral)
                                         |
                                         v
                           [FASE 5: Proxy de Desenmascarado]
                                         |
                                         v
                         [FASE 6: Flujo de Doble Autorización]
```

### Fase 2: Resolución de Entidades de Alta Precisión

**Normalización difusa y emparejamiento:** Los sufijos legales corporativos (GmbH, AG, Ltd., LLC) se eliminan mediante regex. La cadena normalizada se evalúa contra el `EntityRegistry` usando `rapidfuzz.fuzz.ratio`.

**Guardrail de diseño:** Se prohíbe explícitamente `fuzz.WRatio`. WRatio devuelve 90/100 al comparar "Wirecard" con "Wirecard Asia Pacific Pte Ltd" por contención de subcadenas. Auto-resolver esto fusionaría una filial offshore con su matriz, destruyendo la separación arquitectónica necesaria para detectar fraudes de layering.

* Si `fuzz.ratio > 90`, la mención se mapea automáticamente al `Node_ID` existente.
* **Selección LLM con lista cerrada:** Si la puntuación cae por debajo de 90, interviene el Agente 2 (EntityResolver).

### Calibración Cold-Start en Onboarding (Burn-In Sintético)

Durante el onboarding de Layer 2, el sistema genera 20 titulares sintéticos rutinarios vía LLM, calcula sus distancias de coseno respecto a $m_0$ y pasa el array al método `.seed()` del detector Page-Hinkley. El contador $n$ queda bloqueado en 20 para amortiguar el primer evento real ($1/21$ en lugar de $1/1$).

---

## 6. IMPLEMENTACIÓN COMPLETA DEL MOTOR DE PRODUCCIÓN (PYTHON)

Este script contiene la especificación de código unificada y operativa. Incorpora el enmascaramiento GDPR, la propagación de riesgo dirigida en grafos, la corriente transaccional con desviaciones numéricas y la máquina de estados de gobernanza para la demo del hackathon.

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


def generate_synthetic_baseline(
    company_profile: str,
    m0: List[float],
    embed_fn: Callable[[str], List[float]],
    llm_fn: Callable[[str], str],
    k: int = 20,
) -> List[float]:
    """Genera un array sintético de dominio cerrado para calibrar el ruido del perfil base."""
    prompt = (
        f"Genera una lista limpia de exactamente {k} titulares cortos y rutinarios "
        f"esperados para este perfil empresarial:\n{company_profile}\n\n"
        f"Formato requerido: Devuelve estrictamente un array JSON de strings. "
        f"No añadas bloques markdown, intros ni descripciones."
    )
    raw_output = llm_fn(prompt)
    snippets = json.loads(raw_output)
    return [cosine_distance(embed_fn(s), m0) for s in snippets]


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
