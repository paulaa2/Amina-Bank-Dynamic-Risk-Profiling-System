/**
 * Typed API client for the pKYC FastAPI backend.
 * Base URL is configured via NEXT_PUBLIC_API_URL (defaults to localhost:8000).
 *
 * A module-level session cache prevents repeated Ollama calls when navigating
 * between pages within the same browser session.
 */

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

// ── Backend JSON types (matching _report_to_dict output) ─────────────────────

export interface CompanyListItem {
  id: number;
  legal_name: string;
  country: string;
  baseline_risk_rating: string;
}

export interface LiveTopologyContributor {
  name: string;
  /** Backend emits UPPERCASE ("PERSON", "COMPANY") */
  type: string;
  relation: string;
  intrinsic_risk: number;
  contributed: number;
}

export interface LiveNewGraphNode {
  node_id: string;
  name: string;
  type: string;
  intrinsic_risk: number;
  relation: string;
  control_weight: number;
  /** True when the node was created during this run; false when an existing KYC node received a new edge. */
  is_new?: boolean;
}

export interface LiveEvent {
  title: string;
  masked_title: string;
  extracted_fact: string;
  triaged_in: boolean;
  scenario_index?: number;
  date?: string;
  source?: string;
  url?: string;
  evidence?: string;
  semantic_distance: number;
  topology_signal?: number;
  behavioral_signal?: number;
  stream_statistics?: Record<string, number>;
  stream_ratios?: Record<string, number>;
  combined_risk: number;
  alarms: Record<string, boolean>;
  new_graph_nodes: LiveNewGraphNode[];
}

export interface LiveGovernance {
  alert_id: string;
  target_entity_id: string;
  target_display_name: string;
  risk_score: number;
  trigger_streams: string[];
  status: string;
  assigned_analyst: string;
  proposed_mitigation_action: string;
  compliance_approver: string;
  audit_trail: Array<{
    timestamp: string;
    user: string;
    action: string;
    resulting_status: string;
  }>;
}

export interface LiveReport {
  /** Added by the API layer (not in the native pipeline output) */
  id: string;
  client: {
    legal_name: string;
    country: string;
    jurisdiction: string;
    baseline_risk_rating: string;
    expected_business_model: string;
    known_graph_nodes: number;
  };
  security: {
    masked_entities: number;
    company_token: string;
    note: string;
  };
  topology: {
    company_exposure: number;
    circular_ownership_detected: boolean;
    top_contributors: LiveTopologyContributor[];
  };
  streams: {
    bonferroni_scale: number;
    semantic: { last_statistic: number; threshold: number };
    topology: { last_statistic: number; threshold: number; observed_exposure: number };
    behavioral_tx: { last_statistic: number; threshold: number };
  };
  decision: {
    alarm_fired: boolean;
    max_combined_risk: number;
    threshold: number;
    triggering_event: string | null;
  };
  cost: {
    events_seen: number;
    events_passed_triage: number;
    events_embedded: number;
    cloud_reports_generated: number;
    local_tokens: { prompt: number; completion: number; cost_usd: number };
    cloud_tokens: { prompt: number; completion: number; cost_usd: number };
    projected_cloud_cost_per_1000_analyses_usd: number;
    stage_calls: Record<string, number>;
  };
  governance: LiveGovernance | null;
  warnings: string[];
  events: LiveEvent[];
  report_markdown: string | null;
  scenario?: {
    scenario_id: string;
    description?: string;
    reference_model?: string;
    curated_event_count?: number;
    processed_event_count?: number;
  };
}

export interface ReplayScenarioItem {
  scenario_id: string;
  client: string;
  description: string;
  reference_model: string;
  event_count: number;
  company_id: number | null;
}

export interface GlobalScenarioItem {
  id: string;
  name: string;
  description: string;
  companies: string[];
  expected_contagion: string;
  max_events: number;
}

export interface GlobalContagionEvent {
  type: "inherited" | "published" | "frozen" | "event" | string;
  target?: string;
  source?: string;
  entity?: string;
  risk?: number;
  trigger?: boolean;
  title?: string;
}

export interface GlobalDemoResult {
  scenario_id: string;
  scenario_name: string;
  scenario_description: string;
  expected_contagion: string;
  companies: string[];
  company_ids: Record<string, number>;
  shared_threat_memory: Record<string, number>;
  contagion_events: GlobalContagionEvent[];
  clients: Record<string, LiveReport>;
}

// ── Session cache ─────────────────────────────────────────────────────────────

const _cache = new Map<string, LiveReport>();

function cacheKey(id: number, simulateTx: boolean) {
  return `${id}_${simulateTx}`;
}

export function getCachedReport(id: number): LiveReport | null {
  return _cache.get(cacheKey(id, false)) ?? null;
}

export function getAllCachedReports(): LiveReport[] {
  return Array.from(_cache.values());
}

export type GovernanceAction =
  | "APPROVE_FREEZE"
  | "APPROVE_ENHANCED_DD"
  | "DISMISS_FALSE_POSITIVE";

/**
 * Record an operator action against a pending alert.
 * Returns the updated report (governance status advanced, audit trail extended).
 */
export async function takeGovernanceAction(
  id: number,
  action: GovernanceAction,
  operator = "compliance_operator"
): Promise<LiveReport> {
  const res = await fetch(`${API_BASE}/api/analyze/${id}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, operator }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Action failed");
  }
  const updated: LiveReport = await res.json();
  // Update session cache so the dossier page reflects the new status immediately
  _cache.set(cacheKey(id, false), updated);
  return updated;
}

// ── Scheduler ─────────────────────────────────────────────────────────────────

export interface SchedulerStatus {
  running:          boolean;
  schedule:         string;
  next_run:         string | null;
  last_run:         string | null;
  run_in_progress:  boolean;
  cached_companies: number;
}

export interface BackendCacheStatus {
  cached_ids: string[];
  count: number;
}

export async function getBackendCacheStatus(): Promise<BackendCacheStatus> {
  const res = await fetch(`${API_BASE}/api/cache`);
  if (!res.ok) throw new Error("Failed to fetch backend cache status");
  return res.json();
}

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetch(`${API_BASE}/api/scheduler/status`);
  if (!res.ok) throw new Error("Failed to fetch scheduler status");
  return res.json();
}

export async function triggerScheduledRun(): Promise<{ status: string; message: string; started_at: string }> {
  const res = await fetch(`${API_BASE}/api/scheduler/run-now`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Failed to trigger run");
  }
  return res.json();
}

// ── SSE streaming types ───────────────────────────────────────────────────────

export interface BaselineStreamData {
  id: string;
  client: LiveReport["client"];
  security: LiveReport["security"];
  topology: LiveReport["topology"];
  stream_thresholds?: {
    bonferroni_scale: number;
    semantic: number;
    topology: number;
    behavioral_tx: number;
  };
}

export interface ExtractionStreamData {
  event_title: string;
  source: string;
  adverse_score: number;
  new_nodes: LiveNewGraphNode[];
}

export interface RiskStreamData {
  event_title: string;
  semantic: number;
  topology: number;
  behavioral_tx: number;
  r_combined: number;
  alarms: Record<string, boolean>;
  contributors: LiveTopologyContributor[];
}

export type StreamEvent =
  | { event: "baseline";          data: BaselineStreamData }
  | { event: "extraction";        data: ExtractionStreamData }
  | { event: "risk_calculated";   data: RiskStreamData }
  | { event: "report_generating"; data: Record<string, never> }
  | { event: "complete";          data: LiveReport }
  | { event: "error";             data: { message: string } };

/**
 * Stream the pKYC analysis for one company via Server-Sent Events.
 *
 * Calls `onEvent` for every milestone the backend yields.
 * Automatically populates the session cache on "complete".
 * Pass an AbortSignal to cancel mid-stream (e.g. on component unmount).
 */
export async function analyzeCompanyStream(
  id: number,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  forceRefresh = false,
  simulateTx = false,
): Promise<void> {
  const params = new URLSearchParams();
  if (forceRefresh) params.set("force_refresh", "true");
  if (simulateTx) params.set("simulate_tx_anomaly", "true");
  const qs = params.toString();
  const url  = `${API_BASE}/api/analyze/${id}/stream${qs ? `?${qs}` : ""}`;
  const res  = await fetch(url, { signal });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("Response body is not readable");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const jsonStr = trimmed.slice(5).trim();
        if (!jsonStr) continue;
        try {
          const parsed = JSON.parse(jsonStr) as StreamEvent;
          if (parsed.event === "complete") {
            _cache.set(cacheKey(id, false), parsed.data);
          }
          onEvent(parsed);
        } catch {
          /* skip malformed SSE chunks */
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function invalidateCache(id?: number): void {
  if (id !== undefined) {
    _cache.delete(cacheKey(id, false));
    _cache.delete(cacheKey(id, true));
  } else {
    _cache.clear();
  }
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

/** Returns true if the Python API server is reachable. */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Fast: reads directly from SQLite, no Ollama involved. */
export async function listCompanies(): Promise<CompanyListItem[]> {
  const res = await fetch(`${API_BASE}/api/companies`);
  if (!res.ok) throw new Error(`listCompanies: ${res.status} ${res.statusText}`);
  return res.json();
}

export interface AnalyzeOptions {
  max_events?: number;
  simulate_tx_anomaly?: boolean;
  force_refresh?: boolean;
}

/**
 * Trigger a full pKYC analysis for one company.
 * Expect 15–60 s on first call; cached results return in ~200 ms.
 */
export async function analyzeCompany(
  id: number,
  opts: AnalyzeOptions = {}
): Promise<LiveReport> {
  const res = await fetch(`${API_BASE}/api/analyze/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      max_events: opts.max_events ?? 5,
      simulate_tx_anomaly: opts.simulate_tx_anomaly ?? false,
      force_refresh: opts.force_refresh ?? false,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Analysis failed");
  }
  const report: LiveReport = await res.json();
  _cache.set(cacheKey(id, opts.simulate_tx_anomaly ?? false), report);
  return report;
}

/**
 * Serve from the session cache if available, otherwise run the full analysis.
 * Use this on the Client Dossier page so navigating back is instant.
 */
export async function analyzeCompanyCached(
  id: number,
  opts: AnalyzeOptions = {}
): Promise<LiveReport> {
  const key = cacheKey(id, opts.simulate_tx_anomaly ?? false);
  if (_cache.has(key) && !opts.force_refresh) {
    return _cache.get(key)!;
  }
  return analyzeCompany(id, opts);
}

/** Return a cached LiveReport if the API has one (404 → null). */
export async function getCachedAnalysis(id: number): Promise<LiveReport | null> {
  const res = await fetch(`${API_BASE}/api/analyze/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `getCachedAnalysis: ${res.status}`);
  }
  const report: LiveReport = await res.json();
  _cache.set(cacheKey(id, false), report);
  return report;
}

/** List curated historical scenarios (same as ``run_scenario_demo``). */
export async function listReplayScenarios(): Promise<ReplayScenarioItem[]> {
  const res = await fetch(`${API_BASE}/api/scenarios/replay`);
  if (!res.ok) throw new Error(`listReplayScenarios: ${res.status} ${res.statusText}`);
  return res.json();
}

/**
 * Replay a curated scenario and return a LiveReport with graph mutations in
 * ``events[].new_graph_nodes`` (for the corporate graph visualisation).
 */
export async function replayScenario(
  scenarioId: string,
  opts: { force_refresh?: boolean } = {},
): Promise<LiveReport> {
  const qs = opts.force_refresh ? "?force_refresh=true" : "";
  const res = await fetch(`${API_BASE}/api/scenario-replay/${scenarioId}${qs}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Scenario replay failed");
  }
  const report: LiveReport = await res.json();
  if (report.id) {
    _cache.set(cacheKey(Number(report.id), false), report);
  }
  return report;
}

/** List cross-client contagion demos (same as ``run_global_demo`` presets). */
export async function listGlobalScenarios(): Promise<GlobalScenarioItem[]> {
  const res = await fetch(`${API_BASE}/api/scenarios`);
  if (!res.ok) throw new Error(`listGlobalScenarios: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Run a cross-client contagion demo and return the structured orchestrator trace. */
export async function runGlobalScenario(
  scenarioId: string,
  opts: { force_refresh?: boolean; max_events?: number } = {},
): Promise<GlobalDemoResult> {
  const res = await fetch(`${API_BASE}/api/global-demo/scenario/${scenarioId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      force_refresh: opts.force_refresh ?? false,
      max_events: opts.max_events,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? "Global demo failed");
  }
  return res.json();
}
