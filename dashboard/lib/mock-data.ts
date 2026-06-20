// ─────────────────────────────────────────────────────────────────────────────
// TypeScript interfaces mirroring the backend EngineReport JSON contract
// (src/run_demo.py → _report_to_dict)
// ─────────────────────────────────────────────────────────────────────────────

export type RiskRating = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type GovernanceStatus =
  | "DETECTED"
  | "UNDER_REVIEW"
  | "FOUR_EYES_PENDING"
  | "RESOLVED_MITIGATED"
  | "ESCALATED_TO_REGULATOR";
export type AlertLevel = "Critical" | "Medium" | "Low";
export type NodeType = "company" | "person" | "subsidiary" | "jurisdiction";
export type RelationType =
  | "DIRECTS"
  | "OWNS"
  | "SUBSIDIARY_OF"
  | "REGISTERED_IN";

// ── Core domain ──────────────────────────────────────────────────────────────

export interface ClientProfile {
  legal_name: string;
  country: string;
  jurisdiction: string;
  baseline_risk_rating: RiskRating;
  expected_business_model: string;
  known_graph_nodes: number;
}

export interface SecurityInfo {
  masked_entities: number;
  company_token: string;
  note: string;
}

export interface TopologyContributor {
  name: string;
  type: "person" | "company";
  relation: RelationType;
  intrinsic_risk: number; // 0–1
  contributed: number;
}

export interface TopologyInfo {
  company_exposure: number; // 0–1
  circular_ownership_detected: boolean;
  top_contributors: TopologyContributor[];
}

export interface StreamMetric {
  last_statistic: number;
  threshold: number;
}

export interface TopologyStreamMetric extends StreamMetric {
  observed_exposure: number;
}

export interface Streams {
  bonferroni_scale: number;
  semantic: StreamMetric;
  topology: TopologyStreamMetric;
  behavioral_tx: StreamMetric;
}

export interface Decision {
  alarm_fired: boolean;
  max_combined_risk: number; // 0–1  →  "Unified Alert Level"
  threshold: number;
  triggering_event: string;
}

export interface AuditEntry {
  timestamp: string; // ISO-8601
  user: string;
  action: string;
  resulting_status: GovernanceStatus | string;
}

export interface Governance {
  alert_id: string;
  target_entity_id: string;
  target_display_name: string;
  risk_score: number;
  trigger_streams: Array<"semantic" | "topology" | "behavioral_tx">;
  status: GovernanceStatus;
  assigned_analyst: string;
  proposed_mitigation_action: string;
  compliance_approver: string;
  audit_trail: AuditEntry[];
}

export interface KycEvent {
  title: string;
  triaged_in: boolean;
  semantic_distance: number;
  combined_risk: number;
  alarms: {
    semantic?: boolean;
    topology?: boolean;
    behavioral_tx?: boolean;
  };
}

export interface CostInfo {
  events_seen: number;
  events_passed_triage: number;
  events_embedded: number;
  cloud_reports_generated: number;
  local_tokens: { prompt: number; completion: number; cost_usd: number };
  cloud_tokens: { prompt: number; completion: number; cost_usd: number };
  projected_cloud_cost_per_1000_analyses_usd: number;
  stage_calls: { sentinel_extract: number; embedding: number };
}

export interface EngineReport {
  id: string;
  client: ClientProfile;
  security: SecurityInfo;
  topology: TopologyInfo;
  streams: Streams;
  decision: Decision;
  cost: CostInfo;
  governance: Governance | null;
  warnings: string[];
  events: KycEvent[];
  report_markdown: string | null;
}

// ── UI-layer helpers ─────────────────────────────────────────────────────────

/** Used in the Alert Inbox table on the Control Room */
export interface AlertRow {
  clientId: string;
  name: string;
  maskedName: string;
  alertLevel: AlertLevel;
  /** Human-readable trigger (maps from trigger_streams) */
  triggerReason: string;
  timestamp: string;
  riskScore: number;
}

/** ReactFlow graph node */
export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  intrinsicRisk: number; // 0–1
  position: { x: number; y: number };
}

/** ReactFlow graph edge */
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

/** Recharts time-series point for Business Model Drift */
export interface DriftPoint {
  date: string;
  driftScore: number; // Page-Hinkley statistic (0–1 normalised)
  threshold: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// MOCK DATA
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_REPORTS: Record<string, EngineReport> = {
  "1": {
    id: "1",
    client: {
      legal_name: "Wirecard AG",
      country: "DE",
      jurisdiction: "DE-BY",
      baseline_risk_rating: "CRITICAL",
      expected_business_model:
        "Payment processing and financial technology services.",
      known_graph_nodes: 6,
    },
    security: {
      masked_entities: 6,
      company_token: "MASKED_COMPANY_001",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.91,
      circular_ownership_detected: true,
      top_contributors: [
        {
          name: "Markus Braun",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.95,
          contributed: 0.42,
        },
        {
          name: "Jan Marsalek",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.98,
          contributed: 0.38,
        },
        {
          name: "Wirecard Bank AG",
          type: "company",
          relation: "SUBSIDIARY_OF",
          intrinsic_risk: 0.78,
          contributed: 0.11,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.98,
      semantic: { last_statistic: 0.88, threshold: 0.82 },
      topology: {
        last_statistic: 0.91,
        threshold: 0.15,
        observed_exposure: 0.91,
      },
      behavioral_tx: { last_statistic: 2.4, threshold: 1.2 },
    },
    decision: {
      alarm_fired: true,
      max_combined_risk: 0.94,
      threshold: 0.5,
      triggering_event:
        "Wirecard AG executives under investigation for €1.9B balance sheet fraud.",
    },
    cost: {
      events_seen: 30,
      events_passed_triage: 14,
      events_embedded: 14,
      cloud_reports_generated: 1,
      local_tokens: { prompt: 6200, completion: 1100, cost_usd: 0.0 },
      cloud_tokens: { prompt: 1200, completion: 800, cost_usd: 0.0016 },
      projected_cloud_cost_per_1000_analyses_usd: 0.06,
      stage_calls: { sentinel_extract: 14, embedding: 15 },
    },
    governance: {
      alert_id: "ALT_001",
      target_entity_id: "COMPANY_1",
      target_display_name: "Wirecard AG",
      risk_score: 0.94,
      trigger_streams: ["semantic", "topology", "behavioral_tx"],
      status: "ESCALATED_TO_REGULATOR",
      assigned_analyst: "analyst_clara",
      proposed_mitigation_action: "FREEZE_ASSETS",
      compliance_approver: "officer_marcus",
      audit_trail: [
        {
          timestamp: "2026-06-18T08:14:00Z",
          user: "system",
          action: "Alert detected by drift fusion gateway",
          resulting_status: "DETECTED",
        },
        {
          timestamp: "2026-06-18T08:45:00Z",
          user: "analyst_clara",
          action: "Case assigned for four-eyes review",
          resulting_status: "UNDER_REVIEW",
        },
        {
          timestamp: "2026-06-18T10:02:00Z",
          user: "officer_marcus",
          action: "Escalated to regulator — circular ownership confirmed",
          resulting_status: "ESCALATED_TO_REGULATOR",
        },
      ],
    },
    warnings: [],
    events: [
      {
        title: "Wirecard AG annual report delayed for third year",
        triaged_in: true,
        semantic_distance: 0.71,
        combined_risk: 0.94,
        alarms: { semantic: true, topology: true, behavioral_tx: true },
      },
      {
        title: "Munich prosecutors open fraud investigation against Wirecard",
        triaged_in: true,
        semantic_distance: 0.88,
        combined_risk: 0.92,
        alarms: { semantic: true, topology: true, behavioral_tx: false },
      },
      {
        title: "Software company releases Q3 results",
        triaged_in: false,
        semantic_distance: 0.0,
        combined_risk: 0.0,
        alarms: {},
      },
    ],
    report_markdown: `# AML Compliance Report — Alert ALT_001\n\n**Entity:** Wirecard AG \n**Date:** 2026-06-18 \n**Risk Score:** 0.94 (CRITICAL)\n\n---\n\n## Executive Summary\n\nWirecard AG presents a **critical risk profile** based on convergent signals across all three monitoring streams. The semantic drift detector identified a fundamental departure from the entity's baseline business model (payment processing), now dominated by litigation, asset concealment, and regulatory evasion activity.\n\n## Key Risk Indicators\n\n- **Business Model Drift (Semantic):** Score 0.88 — far exceeds the 0.82 threshold. Public narrative has shifted from core fintech operations to balance-sheet fraud.\n- **Third-Party Exposure (Topology):** 91% network contamination. Two board directors (Braun, Marsalek) carry individual risk scores above 0.95. Circular ownership structure detected.\n- **Transaction Anomalies (Behavioral):** Statistic 2.4× above threshold. Unusual cash flow patterns consistent with asset-stripping.\n\n## Recommended Action\n\n**FREEZE ASSETS** and **ESCALATE TO REGULATOR** immediately. Four-eyes approval obtained from compliance officer (officer_marcus).\n\n---\n*Generated by AMINA Bank pKYC Engine v1.0 — CONFIDENTIAL*`,
  },

  "2": {
    id: "2",
    client: {
      legal_name: "FTX Trading Ltd",
      country: "BS",
      jurisdiction: "BS-NP",
      baseline_risk_rating: "CRITICAL",
      expected_business_model: "Cryptocurrency exchange and derivatives trading.",
      known_graph_nodes: 5,
    },
    security: {
      masked_entities: 5,
      company_token: "MASKED_COMPANY_002",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.87,
      circular_ownership_detected: false,
      top_contributors: [
        {
          name: "Sam Bankman-Fried",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.99,
          contributed: 0.51,
        },
        {
          name: "Alameda Research LLC",
          type: "company",
          relation: "SUBSIDIARY_OF",
          intrinsic_risk: 0.92,
          contributed: 0.36,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.8,
      semantic: { last_statistic: 0.84, threshold: 0.82 },
      topology: {
        last_statistic: 0.87,
        threshold: 0.15,
        observed_exposure: 0.87,
      },
      behavioral_tx: { last_statistic: 1.9, threshold: 1.2 },
    },
    decision: {
      alarm_fired: true,
      max_combined_risk: 0.91,
      threshold: 0.5,
      triggering_event:
        "FTX halts withdrawals amid $8B customer fund shortfall.",
    },
    cost: {
      events_seen: 28,
      events_passed_triage: 12,
      events_embedded: 12,
      cloud_reports_generated: 1,
      local_tokens: { prompt: 5800, completion: 950, cost_usd: 0.0 },
      cloud_tokens: { prompt: 1100, completion: 750, cost_usd: 0.0014 },
      projected_cloud_cost_per_1000_analyses_usd: 0.05,
      stage_calls: { sentinel_extract: 12, embedding: 13 },
    },
    governance: {
      alert_id: "ALT_002",
      target_entity_id: "COMPANY_2",
      target_display_name: "FTX Trading Ltd",
      risk_score: 0.91,
      trigger_streams: ["semantic", "topology", "behavioral_tx"],
      status: "RESOLVED_MITIGATED",
      assigned_analyst: "analyst_thomas",
      proposed_mitigation_action: "FREEZE_ASSETS",
      compliance_approver: "officer_anna",
      audit_trail: [
        {
          timestamp: "2026-06-17T14:30:00Z",
          user: "system",
          action: "Alert detected by drift fusion gateway",
          resulting_status: "DETECTED",
        },
        {
          timestamp: "2026-06-17T15:10:00Z",
          user: "analyst_thomas",
          action: "Manual review initiated",
          resulting_status: "UNDER_REVIEW",
        },
        {
          timestamp: "2026-06-17T16:44:00Z",
          user: "officer_anna",
          action: "Assets frozen — mitigation approved",
          resulting_status: "RESOLVED_MITIGATED",
        },
      ],
    },
    warnings: [],
    events: [
      {
        title: "FTX suspends customer withdrawals citing liquidity crunch",
        triaged_in: true,
        semantic_distance: 0.84,
        combined_risk: 0.91,
        alarms: { semantic: true, topology: true, behavioral_tx: true },
      },
      {
        title: "Binance withdraws from FTX acquisition talks",
        triaged_in: true,
        semantic_distance: 0.76,
        combined_risk: 0.78,
        alarms: { semantic: true, topology: false, behavioral_tx: true },
      },
    ],
    report_markdown: `# AML Compliance Report — Alert ALT_002\n\n**Entity:** FTX Trading Ltd \n**Date:** 2026-06-17 \n**Risk Score:** 0.91 (CRITICAL)\n\n---\n\n## Executive Summary\n\nFTX Trading Ltd has triggered all three monitoring streams simultaneously. The convergence of semantic drift, third-party network contamination, and anomalous transaction patterns indicates a **systemic integrity failure**.\n\n## Key Risk Indicators\n\n- **Business Model Drift:** Core narrative shifted from exchange operations to customer fund misappropriation.\n- **Third-Party Exposure:** CEO (SBF) carries a 0.99 intrinsic risk score; Alameda Research (affiliated entity) shows 0.92 risk.\n- **Transaction Anomalies:** Withdrawal halts and intercompany transfers detected.\n\n## Recommended Action\n\n**FREEZE ASSETS** approved. Case escalation to US regulators coordinated.\n\n---\n*Generated by AMINA Bank pKYC Engine v1.0 — CONFIDENTIAL*`,
  },

  "3": {
    id: "3",
    client: {
      legal_name: "MicroStrategy Incorporated",
      country: "US",
      jurisdiction: "US-VA",
      baseline_risk_rating: "MEDIUM",
      expected_business_model:
        "Enterprise business intelligence software and cloud analytics.",
      known_graph_nodes: 4,
    },
    security: {
      masked_entities: 4,
      company_token: "MASKED_COMPANY_003",
      note: "All Layer-1 text is processed locally on masked tokens.",
      },
    topology: {
      company_exposure: 0.12,
      circular_ownership_detected: false,
      top_contributors: [
        {
          name: "Michael Saylor",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.22,
          contributed: 0.08,
        },
        {
          name: "Phong Le",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.05,
          contributed: 0.04,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.1,
      semantic: { last_statistic: 0.62, threshold: 0.82 },
      topology: {
        last_statistic: 0.12,
        threshold: 0.15,
        observed_exposure: 0.12,
      },
      behavioral_tx: { last_statistic: 0.3, threshold: 1.2 },
    },
    decision: {
      alarm_fired: true,
      max_combined_risk: 0.62,
      threshold: 0.5,
      triggering_event:
        "MicroStrategy acquires additional 21,000 Bitcoin — total treasury exceeds $10B.",
    },
    cost: {
      events_seen: 25,
      events_passed_triage: 8,
      events_embedded: 8,
      cloud_reports_generated: 1,
      local_tokens: { prompt: 4200, completion: 800, cost_usd: 0.0 },
      cloud_tokens: { prompt: 900, completion: 600, cost_usd: 0.001 },
      projected_cloud_cost_per_1000_analyses_usd: 0.04,
      stage_calls: { sentinel_extract: 8, embedding: 9 },
    },
    governance: {
      alert_id: "ALT_003",
      target_entity_id: "COMPANY_3",
      target_display_name: "MicroStrategy Incorporated",
      risk_score: 0.62,
      trigger_streams: ["semantic"],
      status: "UNDER_REVIEW",
      assigned_analyst: "analyst_clara",
      proposed_mitigation_action: "ENHANCED_DUE_DILIGENCE",
      compliance_approver: "officer_marcus",
      audit_trail: [
        {
          timestamp: "2026-06-20T09:00:00Z",
          user: "system",
          action: "Business model drift detected — semantic stream",
          resulting_status: "DETECTED",
        },
        {
          timestamp: "2026-06-20T09:30:00Z",
          user: "analyst_clara",
          action: "Case opened for enhanced due diligence review",
          resulting_status: "UNDER_REVIEW",
        },
      ],
    },
    warnings: [],
    events: [
      {
        title: "MicroStrategy adds 21,000 Bitcoin to corporate treasury",
        triaged_in: true,
        semantic_distance: 0.62,
        combined_risk: 0.62,
        alarms: { semantic: true, topology: false, behavioral_tx: false },
      },
      {
        title: "Michael Saylor speaks at Bitcoin conference",
        triaged_in: true,
        semantic_distance: 0.44,
        combined_risk: 0.44,
        alarms: { semantic: false, topology: false, behavioral_tx: false },
      },
      {
        title: "BI software market sees consolidation in Q2",
        triaged_in: false,
        semantic_distance: 0.0,
        combined_risk: 0.0,
        alarms: {},
      },
    ],
    report_markdown: `# AML Compliance Report — Alert ALT_003\n\n**Entity:** MicroStrategy Incorporated \n**Date:** 2026-06-20 \n**Risk Score:** 0.62 (MEDIUM)\n\n---\n\n## Executive Summary\n\nMicroStrategy's public narrative has significantly diverged from its baseline business model (enterprise BI software). The semantic drift detector identifies a primary activity shift toward crypto-asset accumulation, which exceeds the monitoring threshold.\n\n## Key Risk Indicators\n\n- **Business Model Drift:** Score 0.62 — above the 0.50 alarm threshold. Core communications now predominantly reference Bitcoin treasury strategy.\n- **Third-Party Exposure:** Low (0.12). No high-risk individuals detected in corporate graph.\n- **Transaction Anomalies:** Within normal range.\n\n## Recommended Action\n\n**Enhanced Due Diligence** — review Bitcoin treasury strategy for AML/CFT exposure. No immediate freeze required.\n\n---\n*Generated by AMINA Bank pKYC Engine v1.0 — CONFIDENTIAL*`,
  },

  "4": {
    id: "4",
    client: {
      legal_name: "OpenAI, Inc.",
      country: "US",
      jurisdiction: "US-CA",
      baseline_risk_rating: "LOW",
      expected_business_model:
        "Artificial intelligence research and product development.",
      known_graph_nodes: 3,
    },
    security: {
      masked_entities: 3,
      company_token: "MASKED_COMPANY_004",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.04,
      circular_ownership_detected: false,
      top_contributors: [
        {
          name: "Sam Altman",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.08,
          contributed: 0.03,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.1,
      semantic: { last_statistic: 0.21, threshold: 0.82 },
      topology: {
        last_statistic: 0.04,
        threshold: 0.15,
        observed_exposure: 0.04,
      },
      behavioral_tx: { last_statistic: 0.1, threshold: 1.2 },
    },
    decision: {
      alarm_fired: false,
      max_combined_risk: 0.21,
      threshold: 0.5,
      triggering_event: "",
    },
    cost: {
      events_seen: 18,
      events_passed_triage: 4,
      events_embedded: 4,
      cloud_reports_generated: 0,
      local_tokens: { prompt: 2100, completion: 320, cost_usd: 0.0 },
      cloud_tokens: { prompt: 0, completion: 0, cost_usd: 0.0 },
      projected_cloud_cost_per_1000_analyses_usd: 0.0,
      stage_calls: { sentinel_extract: 4, embedding: 4 },
    },
    governance: null,
    warnings: [],
    events: [
      {
        title: "OpenAI launches GPT-5 for enterprise customers",
        triaged_in: true,
        semantic_distance: 0.21,
        combined_risk: 0.21,
        alarms: { semantic: false, topology: false, behavioral_tx: false },
      },
      {
        title: "AI regulation bill advances in US Senate",
        triaged_in: false,
        semantic_distance: 0.0,
        combined_risk: 0.0,
        alarms: {},
      },
    ],
    report_markdown: null,
  },

  "5": {
    id: "5",
    client: {
      legal_name: "VTB Bank",
      country: "RU",
      jurisdiction: "RU-MOW",
      baseline_risk_rating: "HIGH",
      expected_business_model:
        "State-owned commercial banking and financial services.",
      known_graph_nodes: 7,
    },
    security: {
      masked_entities: 7,
      company_token: "MASKED_COMPANY_005",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.83,
      circular_ownership_detected: false,
      top_contributors: [
        {
          name: "Andrei Kostin",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.91,
          contributed: 0.44,
        },
        {
          name: "Russian Federation",
          type: "company",
          relation: "OWNS",
          intrinsic_risk: 0.88,
          contributed: 0.39,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.5,
      semantic: { last_statistic: 0.77, threshold: 0.82 },
      topology: {
        last_statistic: 0.83,
        threshold: 0.15,
        observed_exposure: 0.83,
      },
      behavioral_tx: { last_statistic: 0.9, threshold: 1.2 },
    },
    decision: {
      alarm_fired: true,
      max_combined_risk: 0.83,
      threshold: 0.5,
      triggering_event:
        "VTB Bank placed on OFAC SDN list — all transactions sanctioned.",
    },
    cost: {
      events_seen: 22,
      events_passed_triage: 10,
      events_embedded: 10,
      cloud_reports_generated: 1,
      local_tokens: { prompt: 4900, completion: 880, cost_usd: 0.0 },
      cloud_tokens: { prompt: 1050, completion: 700, cost_usd: 0.0012 },
      projected_cloud_cost_per_1000_analyses_usd: 0.05,
      stage_calls: { sentinel_extract: 10, embedding: 11 },
    },
    governance: {
      alert_id: "ALT_005",
      target_entity_id: "COMPANY_5",
      target_display_name: "VTB Bank",
      risk_score: 0.83,
      trigger_streams: ["topology"],
      status: "FOUR_EYES_PENDING",
      assigned_analyst: "analyst_thomas",
      proposed_mitigation_action: "FREEZE_ASSETS",
      compliance_approver: "officer_anna",
      audit_trail: [
        {
          timestamp: "2026-06-19T11:00:00Z",
          user: "system",
          action: "Sanctions match detected — OFAC SDN list",
          resulting_status: "DETECTED",
        },
        {
          timestamp: "2026-06-19T11:30:00Z",
          user: "analyst_thomas",
          action: "Sanction confirmation — four-eyes review pending",
          resulting_status: "FOUR_EYES_PENDING",
        },
      ],
    },
    warnings: ["Entity appears on OFAC SDN List — mandatory freeze required"],
    events: [
      {
        title: "VTB Bank added to US Treasury OFAC sanctions list",
        triaged_in: true,
        semantic_distance: 0.77,
        combined_risk: 0.83,
        alarms: { semantic: false, topology: true, behavioral_tx: false },
      },
    ],
    report_markdown: `# AML Compliance Report — Alert ALT_005\n\n**Entity:** VTB Bank \n**Date:** 2026-06-19 \n**Risk Score:** 0.83 (HIGH)\n\n---\n\n## Executive Summary\n\nVTB Bank has been placed on the OFAC SDN (Specially Designated Nationals) list. The third-party exposure stream flagged state ownership by the Russian Federation and a board chair with a 0.91 intrinsic risk score.\n\n## Key Risk Indicators\n\n- **Third-Party Exposure:** 83% — primary driver is state entity ownership and sanctioned board members.\n- **Sanctions Hit:** Confirmed match against OFAC SDN list.\n\n## Recommended Action\n\n**FREEZE ASSETS** immediately. Mandatory regulatory notification required under AMINA Bank compliance policy.\n\n---\n*Generated by AMINA Bank pKYC Engine v1.0 — CONFIDENTIAL*`,
  },

  "6": {
    id: "6",
    client: {
      legal_name: "Gazprombank",
      country: "RU",
      jurisdiction: "RU-MOW",
      baseline_risk_rating: "HIGH",
      expected_business_model:
        "Commercial banking subsidiary of Gazprom energy conglomerate.",
      known_graph_nodes: 8,
    },
    security: {
      masked_entities: 8,
      company_token: "MASKED_COMPANY_006",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.79,
      circular_ownership_detected: true,
      top_contributors: [
        {
          name: "Andrey Miller",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.85,
          contributed: 0.41,
        },
        {
          name: "Gazprom PJSC",
          type: "company",
          relation: "OWNS",
          intrinsic_risk: 0.82,
          contributed: 0.38,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.4,
      semantic: { last_statistic: 0.69, threshold: 0.82 },
      topology: {
        last_statistic: 0.79,
        threshold: 0.15,
        observed_exposure: 0.79,
      },
      behavioral_tx: { last_statistic: 0.7, threshold: 1.2 },
    },
    decision: {
      alarm_fired: true,
      max_combined_risk: 0.79,
      threshold: 0.5,
      triggering_event:
        "Gazprombank subject to EU sectoral sanctions — energy financing restricted.",
    },
    cost: {
      events_seen: 20,
      events_passed_triage: 9,
      events_embedded: 9,
      cloud_reports_generated: 1,
      local_tokens: { prompt: 4600, completion: 820, cost_usd: 0.0 },
      cloud_tokens: { prompt: 980, completion: 640, cost_usd: 0.0011 },
      projected_cloud_cost_per_1000_analyses_usd: 0.04,
      stage_calls: { sentinel_extract: 9, embedding: 10 },
    },
    governance: {
      alert_id: "ALT_006",
      target_entity_id: "COMPANY_6",
      target_display_name: "Gazprombank",
      risk_score: 0.79,
      trigger_streams: ["topology", "semantic"],
      status: "UNDER_REVIEW",
      assigned_analyst: "analyst_clara",
      proposed_mitigation_action: "FREEZE_ASSETS",
      compliance_approver: "officer_marcus",
      audit_trail: [
        {
          timestamp: "2026-06-19T16:00:00Z",
          user: "system",
          action: "EU sanctions match and topology contagion detected",
          resulting_status: "DETECTED",
        },
        {
          timestamp: "2026-06-19T16:45:00Z",
          user: "analyst_clara",
          action: "Reviewing sectoral sanctions scope",
          resulting_status: "UNDER_REVIEW",
        },
      ],
    },
    warnings: ["Entity subject to EU sectoral sanctions"],
    events: [
      {
        title: "EU imposes additional sanctions on Gazprombank energy financing",
        triaged_in: true,
        semantic_distance: 0.69,
        combined_risk: 0.79,
        alarms: { semantic: false, topology: true, behavioral_tx: false },
      },
    ],
    report_markdown: null,
  },

  "7": {
    id: "7",
    client: {
      legal_name: "Surgutneftegas",
      country: "RU",
      jurisdiction: "RU-KHM",
      baseline_risk_rating: "MEDIUM",
      expected_business_model:
        "Oil and gas extraction, refining, and distribution.",
      known_graph_nodes: 5,
    },
    security: {
      masked_entities: 5,
      company_token: "MASKED_COMPANY_007",
      note: "All Layer-1 text is processed locally on masked tokens.",
    },
    topology: {
      company_exposure: 0.41,
      circular_ownership_detected: false,
      top_contributors: [
        {
          name: "Vladimir Bogdanov",
          type: "person",
          relation: "DIRECTS",
          intrinsic_risk: 0.55,
          contributed: 0.28,
        },
      ],
    },
    streams: {
      bonferroni_scale: 2.1,
      semantic: { last_statistic: 0.38, threshold: 0.82 },
      topology: {
        last_statistic: 0.41,
        threshold: 0.15,
        observed_exposure: 0.41,
      },
      behavioral_tx: { last_statistic: 0.5, threshold: 1.2 },
    },
    decision: {
      alarm_fired: false,
      max_combined_risk: 0.41,
      threshold: 0.5,
      triggering_event: "",
    },
    cost: {
      events_seen: 15,
      events_passed_triage: 5,
      events_embedded: 5,
      cloud_reports_generated: 0,
      local_tokens: { prompt: 2800, completion: 450, cost_usd: 0.0 },
      cloud_tokens: { prompt: 0, completion: 0, cost_usd: 0.0 },
      projected_cloud_cost_per_1000_analyses_usd: 0.0,
      stage_calls: { sentinel_extract: 5, embedding: 5 },
    },
    governance: null,
    warnings: [],
    events: [
      {
        title: "Surgutneftegas Q1 oil output stable amid geopolitical pressure",
        triaged_in: true,
        semantic_distance: 0.38,
        combined_risk: 0.41,
        alarms: { semantic: false, topology: false, behavioral_tx: false },
      },
    ],
    report_markdown: null,
  },
};

// ── Alert Inbox (Control Room) ───────────────────────────────────────────────

function triggerReasonsFor(report: EngineReport): string {
  if (!report.decision.alarm_fired) return "Routine monitoring — no alarm";
  const streams = report.governance?.trigger_streams ?? [];
  const map: Record<string, string> = {
    semantic: "Business Model Drift",
    topology: "Third-Party Exposure",
    behavioral_tx: "Transaction Anomalies",
  };
  return streams.map((s) => map[s] ?? s).join(", ") || "Combined Risk Score";
}

function alertLevelFor(score: number): AlertLevel {
  if (score >= 0.75) return "Critical";
  if (score >= 0.5) return "Medium";
  return "Low";
}

export const MOCK_ALERTS: AlertRow[] = Object.values(MOCK_REPORTS)
  .filter((r) => r.decision.alarm_fired)
  .map((r) => ({
    clientId: r.id,
    name: r.client.legal_name,
    maskedName: r.security.company_token,
    alertLevel: alertLevelFor(r.decision.max_combined_risk),
    triggerReason: triggerReasonsFor(r),
    timestamp: r.governance?.audit_trail[0]?.timestamp ?? "2026-06-20T09:00:00Z",
    riskScore: r.decision.max_combined_risk,
  }))
  .sort((a, b) => b.riskScore - a.riskScore);

// ── Drift time-series (per client, last 30 days) ─────────────────────────────

function generateDriftSeries(
  peakScore: number,
  days = 30,
  threshold = 0.5
): DriftPoint[] {
  const points: DriftPoint[] = [];
  const now = new Date("2026-06-20");
  for (let i = days; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const noise = (Math.random() - 0.5) * 0.06;
    const trend = (peakScore * (days - i)) / days;
    const score = Math.min(1, Math.max(0, trend + noise));
    points.push({
      date: d.toISOString().slice(0, 10),
      driftScore: parseFloat(score.toFixed(3)),
      threshold,
    });
  }
  return points;
}

export const MOCK_DRIFT_SERIES: Record<string, DriftPoint[]> = {
  "1": generateDriftSeries(0.88, 30),
  "2": generateDriftSeries(0.84, 30),
  "3": generateDriftSeries(0.62, 30),
  "4": generateDriftSeries(0.21, 30),
  "5": generateDriftSeries(0.77, 30),
  "6": generateDriftSeries(0.69, 30),
  "7": generateDriftSeries(0.38, 30),
};

// ── Corporate graph (ReactFlow) ──────────────────────────────────────────────

export const MOCK_GRAPHS: Record<
  string,
  { nodes: GraphNode[]; edges: GraphEdge[] }
> = {
  "1": {
    nodes: [
      {
        id: "c1",
        label: "Wirecard AG",
        type: "company",
        intrinsicRisk: 0.94,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Markus Braun",
        type: "person",
        intrinsicRisk: 0.95,
        position: { x: 80, y: 60 },
      },
      {
        id: "p2",
        label: "Jan Marsalek",
        type: "person",
        intrinsicRisk: 0.98,
        position: { x: 520, y: 60 },
      },
      {
        id: "s1",
        label: "Wirecard Bank AG",
        type: "subsidiary",
        intrinsicRisk: 0.78,
        position: { x: 120, y: 330 },
      },
      {
        id: "s2",
        label: "Wirecard Asia Pacific",
        type: "subsidiary",
        intrinsicRisk: 0.65,
        position: { x: 480, y: 330 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c1", label: "DIRECTS" },
      { id: "e2", source: "p2", target: "c1", label: "DIRECTS" },
      { id: "e3", source: "c1", target: "s1", label: "PARENT_OF" },
      { id: "e4", source: "c1", target: "s2", label: "PARENT_OF" },
    ],
  },
  "2": {
    nodes: [
      {
        id: "c2",
        label: "FTX Trading Ltd",
        type: "company",
        intrinsicRisk: 0.91,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Sam Bankman-Fried",
        type: "person",
        intrinsicRisk: 0.99,
        position: { x: 80, y: 60 },
      },
      {
        id: "s1",
        label: "Alameda Research LLC",
        type: "subsidiary",
        intrinsicRisk: 0.92,
        position: { x: 120, y: 330 },
      },
      {
        id: "s2",
        label: "FTX US",
        type: "subsidiary",
        intrinsicRisk: 0.7,
        position: { x: 480, y: 330 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c2", label: "DIRECTS" },
      { id: "e2", source: "c2", target: "s1", label: "CONTROLS" },
      { id: "e3", source: "c2", target: "s2", label: "PARENT_OF" },
    ],
  },
  "3": {
    nodes: [
      {
        id: "c3",
        label: "MicroStrategy Inc.",
        type: "company",
        intrinsicRisk: 0.42,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Michael Saylor",
        type: "person",
        intrinsicRisk: 0.22,
        position: { x: 80, y: 60 },
      },
      {
        id: "p2",
        label: "Phong Le",
        type: "person",
        intrinsicRisk: 0.05,
        position: { x: 520, y: 60 },
      },
      {
        id: "j1",
        label: "Virginia, USA",
        type: "jurisdiction",
        intrinsicRisk: 0.0,
        position: { x: 300, y: 350 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c3", label: "DIRECTS" },
      { id: "e2", source: "p2", target: "c3", label: "DIRECTS" },
      { id: "e3", source: "c3", target: "j1", label: "REGISTERED_IN" },
    ],
  },
  "4": {
    nodes: [
      {
        id: "c4",
        label: "OpenAI, Inc.",
        type: "company",
        intrinsicRisk: 0.08,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Sam Altman",
        type: "person",
        intrinsicRisk: 0.08,
        position: { x: 150, y: 60 },
      },
      {
        id: "j1",
        label: "California, USA",
        type: "jurisdiction",
        intrinsicRisk: 0.0,
        position: { x: 300, y: 350 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c4", label: "DIRECTS" },
      { id: "e2", source: "c4", target: "j1", label: "REGISTERED_IN" },
    ],
  },
  "5": {
    nodes: [
      {
        id: "c5",
        label: "VTB Bank",
        type: "company",
        intrinsicRisk: 0.83,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Andrei Kostin",
        type: "person",
        intrinsicRisk: 0.91,
        position: { x: 80, y: 60 },
      },
      {
        id: "co1",
        label: "Russian Federation",
        type: "company",
        intrinsicRisk: 0.88,
        position: { x: 520, y: 60 },
      },
      {
        id: "s1",
        label: "VTB Capital",
        type: "subsidiary",
        intrinsicRisk: 0.72,
        position: { x: 300, y: 350 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c5", label: "DIRECTS" },
      { id: "e2", source: "co1", target: "c5", label: "OWNS" },
      { id: "e3", source: "c5", target: "s1", label: "PARENT_OF" },
    ],
  },
  "6": {
    nodes: [
      {
        id: "c6",
        label: "Gazprombank",
        type: "company",
        intrinsicRisk: 0.79,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Andrey Miller",
        type: "person",
        intrinsicRisk: 0.85,
        position: { x: 80, y: 60 },
      },
      {
        id: "co1",
        label: "Gazprom PJSC",
        type: "company",
        intrinsicRisk: 0.82,
        position: { x: 520, y: 60 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c6", label: "DIRECTS" },
      { id: "e2", source: "co1", target: "c6", label: "OWNS" },
    ],
  },
  "7": {
    nodes: [
      {
        id: "c7",
        label: "Surgutneftegas",
        type: "company",
        intrinsicRisk: 0.41,
        position: { x: 300, y: 180 },
      },
      {
        id: "p1",
        label: "Vladimir Bogdanov",
        type: "person",
        intrinsicRisk: 0.55,
        position: { x: 150, y: 60 },
      },
      {
        id: "j1",
        label: "Khanty-Mansiysk, RU",
        type: "jurisdiction",
        intrinsicRisk: 0.2,
        position: { x: 300, y: 350 },
      },
    ],
    edges: [
      { id: "e1", source: "p1", target: "c7", label: "DIRECTS" },
      { id: "e2", source: "c7", target: "j1", label: "REGISTERED_IN" },
    ],
  },
};

// ── Audit History ─────────────────────────────────────────────────────────────

export interface AuditHistoryRow {
  id: string;
  timestamp: string;
  user: string;
  action: string;
  clientId: string;
  clientName: string;
  resultingStatus: string;
  alertId: string;
}

export const MOCK_AUDIT_HISTORY: AuditHistoryRow[] = Object.values(MOCK_REPORTS)
  .filter((r) => r.governance !== null)
  .flatMap((r) =>
    (r.governance!.audit_trail as AuditEntry[]).map((entry, idx) => ({
      id: `${r.id}-${idx}`,
      timestamp: entry.timestamp,
      user: entry.user,
      action: entry.action,
      clientId: r.id,
      clientName: r.client.legal_name,
      resultingStatus: entry.resulting_status,
      alertId: r.governance!.alert_id,
    }))
  )
  .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

// ── KPI summary ───────────────────────────────────────────────────────────────

export const MOCK_KPIS = {
  criticalAlertsPending: MOCK_ALERTS.filter((a) => a.alertLevel === "Critical")
    .length,
  entitiesMonitored: Object.keys(MOCK_REPORTS).length,
  avgResponseTimeHours: 1.4,
};
