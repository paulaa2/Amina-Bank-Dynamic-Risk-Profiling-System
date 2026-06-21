/**
 * Typed API client for the pKYC FastAPI backend.
 * Base URL is configured via NEXT_PUBLIC_API_URL (defaults to localhost:8000).
 *
 * A module-level cache plus localStorage persistence prevents repeated Ollama
 * calls when navigating, refreshing, or reopening the dashboard.
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
  is_cached?: boolean;
}

export interface GlobalScenarioItem {
  id: string;
  name: string;
  description: string;
  companies: string[];
  expected_contagion: string;
  max_events: number;
  is_cached?: boolean;
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

const STORAGE_PREFIX = "amina-risk-cache:v4";
/** Bust browser HTTP cache when pinned scenario scores are re-exported. */
const CURATED_STATIC_VERSION = "golden-pinned-20250621";

const _cache = new Map<string, LiveReport>();
const _globalScenarioCache = new Map<string, GlobalDemoResult>();
let _staticScenarioCache: Record<string, LiveReport> | null = null;
let _staticGlobalCache: Record<string, GlobalDemoResult> | null = null;

function staticBasePath(): string {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")) {
    return "/Amina-Bank-Dynamic-Risk-Profiling-System";
  }
  return "";
}

function isValidCuratedReport(report: LiveReport | null | undefined, scenarioId: string): report is LiveReport {
  if (!report?.scenario?.scenario_id || report.scenario.scenario_id !== scenarioId) return false;
  const processed = report.scenario.processed_event_count ?? report.events.length;
  return report.events.length > 0 && report.events.length === processed;
}

function storeCuratedReport(report: LiveReport): void {
  putScenarioReport(report.scenario!.scenario_id!, report);
  if (report.id) {
    putReport(Number(report.id), false, report);
  }
}

async function loadStaticScenarioCache(): Promise<Record<string, LiveReport>> {
  if (_staticScenarioCache) return _staticScenarioCache;
  try {
    const res = await fetch(
      `${staticBasePath()}/api_cache/scenario.json?v=${CURATED_STATIC_VERSION}`,
    );
    if (!res.ok) throw new Error("Static scenario cache not found");
    _staticScenarioCache = (await res.json()) as Record<string, LiveReport>;
    return _staticScenarioCache;
  } catch {
    _staticScenarioCache = {};
    return _staticScenarioCache;
  }
}

async function getCuratedStaticReport(scenarioId: string): Promise<LiveReport | null> {
  const staticCache = await loadStaticScenarioCache();
  const report = staticCache[scenarioId];
  return isValidCuratedReport(report, scenarioId) ? report : null;
}

async function loadStaticGlobalCache(): Promise<Record<string, GlobalDemoResult>> {
  if (_staticGlobalCache) return _staticGlobalCache;
  try {
    const res = await fetch(
      `${staticBasePath()}/api_cache/global.json?v=${CURATED_STATIC_VERSION}`,
    );
    if (!res.ok) throw new Error("Static global cache not found");
    _staticGlobalCache = (await res.json()) as Record<string, GlobalDemoResult>;
    return _staticGlobalCache;
  } catch {
    _staticGlobalCache = {};
    return _staticGlobalCache;
  }
}

async function getStaticGlobalScenario(scenarioId: string): Promise<GlobalDemoResult | null> {
  const staticCache = await loadStaticGlobalCache();
  return staticCache[scenarioId] ?? null;
}

function storageAvailable(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function cacheKey(id: number, simulateTx: boolean) {
  return `${id}_${simulateTx}`;
}

function storageKey(kind: string, key: string): string {
  return `${STORAGE_PREFIX}:${kind}:${key}`;
}

function readStorage<T>(kind: string, key: string): T | null {
  if (!storageAvailable()) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(kind, key));
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStorage<T>(kind: string, key: string, value: T): void {
  if (!storageAvailable()) return;
  try {
    window.localStorage.setItem(storageKey(kind, key), JSON.stringify(value));
  } catch {
    /* localStorage quota/private-mode failures should not break analysis */
  }
}

function deleteStorage(kind: string, key: string): void {
  if (!storageAvailable()) return;
  try {
    window.localStorage.removeItem(storageKey(kind, key));
  } catch {
    /* ignore */
  }
}

function readStoredReports(): LiveReport[] {
  if (!storageAvailable()) return [];
  const reports: LiveReport[] = [];
  for (let i = 0; i < window.localStorage.length; i++) {
    const key = window.localStorage.key(i);
    if (!key?.startsWith(`${STORAGE_PREFIX}:report:`)) continue;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw) reports.push(JSON.parse(raw) as LiveReport);
    } catch {
      /* skip malformed persisted entries */
    }
  }
  return reports;
}

function putReport(id: number, simulateTx: boolean, report: LiveReport): void {
  const key = cacheKey(id, simulateTx);
  _cache.set(key, report);
  writeStorage("report", key, report);
}

function getStoredReport(id: number, simulateTx = false): LiveReport | null {
  const key = cacheKey(id, simulateTx);
  const inMemory = _cache.get(key);
  if (inMemory) return inMemory;
  const stored = readStorage<LiveReport>("report", key);
  if (stored) _cache.set(key, stored);
  return stored;
}

function putScenarioReport(scenarioId: string, report: LiveReport): void {
  writeStorage("scenario", scenarioId, report);
}

export function getStoredScenarioReport(scenarioId: string): LiveReport | null {
  return readStorage<LiveReport>("scenario", scenarioId);
}

/** Load the curated scenario LiveReport for a dossier (shared by Demos + Client pages). */
export async function loadCuratedScenarioReport(
  scenarioId: string,
  companyId?: number,
  opts: { force_refresh?: boolean } = {},
): Promise<LiveReport> {
  if (!opts.force_refresh) {
    // Static export is the source of truth (same pinned scores as Metrics / notebook).
    const staticReport = await getCuratedStaticReport(scenarioId);
    if (staticReport) {
      storeCuratedReport(staticReport);
      return staticReport;
    }

    const cachedScenario = getStoredScenarioReport(scenarioId);
    if (isValidCuratedReport(cachedScenario, scenarioId)) {
      storeCuratedReport(cachedScenario);
      return cachedScenario;
    }

    if (companyId !== undefined) {
      const cachedCompany = getStoredReport(companyId, false);
      if (isValidCuratedReport(cachedCompany, scenarioId)) {
        storeCuratedReport(cachedCompany);
        return cachedCompany;
      }
    }
  }

  return replayScenario(scenarioId, opts);
}

function putGlobalScenario(scenarioId: string, result: GlobalDemoResult): void {
  _globalScenarioCache.set(scenarioId, result);
  writeStorage("global", scenarioId, result);
}

export function getStoredGlobalScenario(scenarioId: string): GlobalDemoResult | null {
  const inMemory = _globalScenarioCache.get(scenarioId);
  if (inMemory) return inMemory;
  const stored = readStorage<GlobalDemoResult>("global", scenarioId);
  if (stored) _globalScenarioCache.set(scenarioId, stored);
  return stored;
}

export function getCachedReport(id: number): LiveReport | null {
  return getStoredReport(id, false);
}

export function getAllCachedReports(): LiveReport[] {
  const byId = new Map<string, LiveReport>();
  for (const [key, report] of _cache.entries()) byId.set(key, report);
  for (const report of readStoredReports()) {
    if (report.id) byId.set(cacheKey(Number(report.id), false), report);
  }
  return Array.from(byId.values());
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
  putReport(id, false, updated);
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
  const cached = getStoredReport(id, simulateTx);
  if (cached && !forceRefresh) {
    onEvent({ event: "complete", data: cached });
    return;
  }

  const params = new URLSearchParams();
  if (forceRefresh) params.set("force_refresh", "true");
  if (simulateTx) params.set("simulate_tx_anomaly", "true");
  const qs = params.toString();
  const url  = `${API_BASE}/api/analyze/${id}/stream${qs ? `?${qs}` : ""}`;

  try {
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
        if (signal?.aborted) break;
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
              putReport(id, simulateTx, parsed.data);
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
  } catch (err) {
    console.warn(`SSE stream for client ${id} failed, attempting simulated streaming from static cache:`, err);
    if (signal?.aborted) return;

    try {
      const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")
        ? "/Amina-Bank-Dynamic-Risk-Profiling-System"
        : "";
      const staticRes = await fetch(`${basePath}/api_cache/analysis.json`);
      if (!staticRes.ok) throw new Error("Static analysis cache not found");
      const data = await staticRes.json();
      const report = data[String(id)] as LiveReport | undefined;
      if (!report) {
        throw new Error(`Company ID ${id} not found in static analysis cache`);
      }

      // Simulate baseline event
      onEvent({
        event: "baseline",
        data: {
          id: report.id,
          client: report.client,
          security: report.security,
          topology: report.topology,
          stream_thresholds: report.streams ? {
            bonferroni_scale: report.streams.bonferroni_scale,
            semantic: report.streams.semantic.threshold,
            topology: report.streams.topology.threshold,
            behavioral_tx: report.streams.behavioral_tx.threshold,
          } : undefined,
        }
      });
      await new Promise(resolve => setTimeout(resolve, 800));
      if (signal?.aborted) return;

      // Yield events one by one to simulate live analysis
      for (const ev of report.events) {
        if (signal?.aborted) return;

        onEvent({
          event: "extraction",
          data: {
            event_title: ev.title,
            source: ev.source || "Static Cache",
            adverse_score: ev.semantic_distance,
            new_nodes: ev.new_graph_nodes || [],
          }
        });
        await new Promise(resolve => setTimeout(resolve, 600));
        if (signal?.aborted) return;

        onEvent({
          event: "risk_calculated",
          data: {
            event_title: ev.title,
            semantic: ev.semantic_distance,
            topology: ev.topology_signal ?? report.topology.company_exposure,
            behavioral_tx: ev.behavioral_signal ?? 0,
            r_combined: ev.combined_risk,
            alarms: ev.alarms,
            contributors: report.topology.top_contributors,
          }
        });
        await new Promise(resolve => setTimeout(resolve, 600));
        if (signal?.aborted) return;
      }

      // Yield complete event
      putReport(id, simulateTx, report);
      onEvent({ event: "complete", data: report });
    } catch (staticErr) {
      console.error("Static simulated streaming failed:", staticErr);
      throw err;
    }
  }
}

export function invalidateCache(id?: number): void {
  if (id !== undefined) {
    _cache.delete(cacheKey(id, false));
    _cache.delete(cacheKey(id, true));
    deleteStorage("report", cacheKey(id, false));
    deleteStorage("report", cacheKey(id, true));
  } else {
    _cache.clear();
    _globalScenarioCache.clear();
    if (storageAvailable()) {
      const keys: string[] = [];
      for (let i = 0; i < window.localStorage.length; i++) {
        const key = window.localStorage.key(i);
        if (key?.startsWith(STORAGE_PREFIX)) keys.push(key);
      }
      for (const key of keys) window.localStorage.removeItem(key);
    }
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
  try {
    const res = await fetch(`${API_BASE}/api/companies`);
    if (!res.ok) throw new Error(`listCompanies: ${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("API listCompanies failed, falling back to static default companies list:", err);
    return [
      { id: 1, legal_name: "Wirecard AG", country: "DE", baseline_risk_rating: "MEDIUM" },
      { id: 2, legal_name: "FTX Trading Ltd", country: "BS", baseline_risk_rating: "HIGH" },
      { id: 3, legal_name: "MicroStrategy Incorporated", country: "US", baseline_risk_rating: "LOW" },
      { id: 4, legal_name: "OpenAI", country: "US", baseline_risk_rating: "LOW" },
      { id: 5, legal_name: "VTB Bank", country: "RU", baseline_risk_rating: "HIGH" },
      { id: 6, legal_name: "Gazprombank", country: "RU", baseline_risk_rating: "HIGH" },
      { id: 7, legal_name: "Surgutneftegas", country: "RU", baseline_risk_rating: "HIGH" },
    ];
  }
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
  const simulateTx = opts.simulate_tx_anomaly ?? false;
  const cached = getStoredReport(id, simulateTx);
  if (cached && !opts.force_refresh) {
    return cached;
  }

  try {
    const res = await fetch(`${API_BASE}/api/analyze/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        max_events: opts.max_events ?? 5,
        simulate_tx_anomaly: simulateTx,
        force_refresh: opts.force_refresh ?? false,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail ?? "Analysis failed");
    }
    const report: LiveReport = await res.json();
    putReport(id, simulateTx, report);
    return report;
  } catch (err) {
    console.warn(`API analyzeCompany ${id} failed, attempting static file fallback:`, err);
    try {
      const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")
        ? "/Amina-Bank-Dynamic-Risk-Profiling-System"
        : "";
      const staticRes = await fetch(`${basePath}/api_cache/analysis.json`);
      if (!staticRes.ok) throw new Error("Static analysis cache not found");
      const data = await staticRes.json();
      const report = data[String(id)];
      if (!report) {
        throw new Error(`Company ID ${id} not found in static analysis cache`);
      }
      putReport(id, simulateTx, report);
      return report;
    } catch (staticErr) {
      console.error("Static file fallback failed:", staticErr);
      throw err;
    }
  }
}

/**
 * Serve from the session cache if available, otherwise run the full analysis.
 * Use this on the Client Dossier page so navigating back is instant.
 */
export async function analyzeCompanyCached(
  id: number,
  opts: AnalyzeOptions = {}
): Promise<LiveReport> {
  const cached = getStoredReport(id, opts.simulate_tx_anomaly ?? false);
  if (cached && !opts.force_refresh) {
    return cached;
  }
  return analyzeCompany(id, opts);
}

/** Return a cached LiveReport if the API has one (404 → null). */
export async function getCachedAnalysis(id: number): Promise<LiveReport | null> {
  const cached = getStoredReport(id, false);
  if (cached) return cached;

  try {
    const res = await fetch(`${API_BASE}/api/analyze/${id}`);
    if (res.status === 404) return null;
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail ?? `getCachedAnalysis: ${res.status}`);
    }
    const report: LiveReport = await res.json();
    putReport(id, false, report);
    return report;
  } catch (err) {
    console.warn(`API getCachedAnalysis for client ${id} failed, attempting static file fallback:`, err);
    try {
      const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")
        ? "/Amina-Bank-Dynamic-Risk-Profiling-System"
        : "";
      const staticRes = await fetch(`${basePath}/api_cache/analysis.json`);
      if (!staticRes.ok) throw new Error("Static analysis cache not found");
      const data = await staticRes.json();
      const report = data[String(id)] as LiveReport | undefined;
      if (!report) return null;
      putReport(id, false, report);
      return report;
    } catch {
      return null;
    }
  }
}

/** List curated historical scenarios (same as ``run_scenario_demo``). */
export async function listReplayScenarios(): Promise<ReplayScenarioItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/scenarios/replay`);
    if (!res.ok) throw new Error(`listReplayScenarios: ${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("API listReplayScenarios failed, falling back to static defaults:", err);
    return [
      {
        scenario_id: "microstrategy_drift",
        client: "MicroStrategy",
        description: "Semantic drift: Enterprise BI software pivoting to a Bitcoin treasury reserve asset.",
        reference_model: "Enterprise Business Intelligence software",
        event_count: 6,
        company_id: 3,
      },
      {
        scenario_id: "wirecard_drift",
        client: "Wirecard",
        description: "Structural accounting fraud and sudden corporate collapse.",
        reference_model: "Licensed payment processing and merchant acquiring.",
        event_count: 6,
        company_id: 1,
      },
      {
        scenario_id: "ftx_rapid_deterioration",
        client: "FTX",
        description: "Evidence-backed rapid deterioration replay: liquidity and governance collapse before bankruptcy.",
        reference_model: "Centralised crypto-asset exchange and custody.",
        event_count: 6,
        company_id: 2,
      },
      {
        scenario_id: "openai_regulatory_drift",
        client: "OpenAI",
        description:
          "Chronological watchlist (6 stream events): Sequoia/FTX cap-table stress, EU privacy, US scrutiny and governance/litigation without crossing 0.5.",
        reference_model: "AI research lab monetising via API and subscriptions.",
        event_count: 6,
        company_id: 4,
      },
      {
        scenario_id: "vtb_sanctions_escalation",
        client: "VTB",
        description: "Sanctions escalation and directed network contagion.",
        reference_model: "State-owned commercial and investment bank.",
        event_count: 5,
        company_id: 5,
      },
      {
        scenario_id: "gazprombank_sanctions_escalation",
        client: "Gazprombank",
        description: "Sovereign risk linkage and European energy payments exposure.",
        reference_model: "Large private/state-linked commercial bank.",
        event_count: 5,
        company_id: 6,
      },
      {
        scenario_id: "surgutneftegas_sanctions_escalation",
        client: "Surgutneftegas",
        description: "Russian energy-sector escalation replay from sectoral controls to full designation.",
        reference_model: "Vertically integrated Russian oil and gas producer.",
        event_count: 4,
        company_id: 7,
      },
    ];
  }
}

/**
 * Replay a curated scenario and return a LiveReport with graph mutations in
 * ``events[].new_graph_nodes`` (for the corporate graph visualisation).
 */
export async function replayScenario(
  scenarioId: string,
  opts: { force_refresh?: boolean } = {},
): Promise<LiveReport> {
  const staticReport = await getCuratedStaticReport(scenarioId);
  if (staticReport) {
    storeCuratedReport(staticReport);
    return staticReport;
  }

  if (!opts.force_refresh) {
    const cachedScenario = getStoredScenarioReport(scenarioId);
    if (isValidCuratedReport(cachedScenario, scenarioId)) {
      storeCuratedReport(cachedScenario);
      return cachedScenario;
    }
  }

  const qs = opts.force_refresh ? "?force_refresh=true" : "";
  try {
    const res = await fetch(`${API_BASE}/api/scenario-replay/${scenarioId}${qs}`, {
      method: "POST",
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail ?? "Scenario replay failed");
    }
    const report: LiveReport = await res.json();
    storeCuratedReport(report);
    return report;
  } catch (err) {
    console.warn(`API replayScenario for ${scenarioId} failed, attempting static file fallback:`, err);
    const report = await getCuratedStaticReport(scenarioId);
    if (!report) {
      throw new Error(`Scenario ID ${scenarioId} not found in static scenario cache`);
    }
    storeCuratedReport(report);
    return report;
  }
}

/** List cross-client contagion demos (same as ``run_global_demo`` presets). */
export async function listGlobalScenarios(): Promise<GlobalScenarioItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/scenarios`);
    if (!res.ok) throw new Error(`listGlobalScenarios: ${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("API listGlobalScenarios failed, falling back to static defaults:", err);
    return [
      {
        id: "russian_sovereign",
        name: "Russian Sovereign Cluster",
        description: "VTB sanctions trigger cross-client contagion: Gazprombank inherits 'Government of Russia' risk (0.15 → 0.90) before processing its own news events.",
        companies: ["VTB", "Gazprombank"],
        expected_contagion: "Government of Russia → Gazprombank",
        max_events: 5,
      },
      {
        id: "vc_contagion",
        name: "VC Investor Contagion",
        description: "FTX collapse publishes Sequoia Capital (risk 0.53). OpenAI, which shares the same institutional investor, inherits elevated Sequoia risk and enters alarm.",
        companies: ["FTX", "OpenAI"],
        expected_contagion: "Sequoia Capital → OpenAI",
        max_events: 5,
      },
      {
        id: "russian_triple",
        name: "Full Russian Triple Cluster",
        description: "VTB and Gazprombank both alarm; Surgutneftegas inherits 'Government of Russia' from the shared threat memory but its own news events fail triage — demonstrating partial propagation.",
        companies: ["VTB", "Gazprombank", "Surgutneftegas"],
        expected_contagion: "Government of Russia → Gazprombank, Surgutneftegas",
        max_events: 5,
      },
    ];
  }
}

/** Run a cross-client contagion demo and return the structured orchestrator trace. */
export async function runGlobalScenario(
  scenarioId: string,
  opts: { force_refresh?: boolean; max_events?: number } = {},
): Promise<GlobalDemoResult> {
  if (opts.max_events === undefined) {
    const staticResult = await getStaticGlobalScenario(scenarioId);
    if (staticResult) {
      putGlobalScenario(scenarioId, staticResult);
      for (const [name, report] of Object.entries(staticResult.clients)) {
        const id = staticResult.company_ids[name] ?? Number(report.id);
        if (id) putReport(id, false, report);
      }
      return staticResult;
    }
  }

  const cached = getStoredGlobalScenario(scenarioId);
  if (cached && !opts.force_refresh && opts.max_events === undefined) {
    return cached;
  }

  try {
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
    const result: GlobalDemoResult = await res.json();
    if (opts.max_events === undefined) {
      putGlobalScenario(scenarioId, result);
    }
    for (const [name, report] of Object.entries(result.clients)) {
      const id = result.company_ids[name] ?? Number(report.id);
      if (id) putReport(id, false, report);
    }
    return result;
  } catch (err) {
    console.warn(`API runGlobalScenario for ${scenarioId} failed, attempting static file fallback:`, err);
    try {
      const basePath = typeof window !== "undefined" && window.location.pathname.startsWith("/Amina-Bank-Dynamic-Risk-Profiling-System")
        ? "/Amina-Bank-Dynamic-Risk-Profiling-System"
        : "";
      const staticRes = await fetch(`${basePath}/api_cache/global.json`);
      if (!staticRes.ok) throw new Error("Static global scenario cache not found");
      const data = await staticRes.json();
      const result = data[scenarioId] as GlobalDemoResult | undefined;
      if (!result) {
        throw new Error(`Global scenario ID ${scenarioId} not found in static global cache`);
      }
      if (opts.max_events === undefined) {
        putGlobalScenario(scenarioId, result);
      }
      for (const [name, report] of Object.entries(result.clients)) {
        const id = result.company_ids[name] ?? Number(report.id);
        if (id) putReport(id, false, report);
      }
      return result;
    } catch (staticErr) {
      console.error("Static global scenario fallback failed:", staticErr);
      throw err;
    }
  }
}
