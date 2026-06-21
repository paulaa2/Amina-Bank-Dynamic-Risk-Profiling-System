"""Layer 2 - simulated internal KYC baseline profiles.

Each entry represents what the bank believed at onboarding.
The 'topology' key defines the initial corporate graph: directors, shareholders,
and subsidiaries that the bank knew about at onboarding time.

For each person/entity in topology, the collector will:
  1. Search news (adverse media scan)
  2. Screen against sanctions/watchlists
  3. Store risk on the TopologyNode
  4. Propagate via directed edge to the company (contagion)

Companies:
  Group A — semantic/structural drift case studies:
    Wirecard AG, FTX Trading Ltd, MicroStrategy, OpenAI
  Group B — actively sanctioned (confirms sanctions + topology collectors):
    VTB Bank, Gazprombank, Surgutneftegas
"""
from __future__ import annotations
import datetime as dt

# rel_type choices (mirror ComplianceDirectedGraph edge weights):
#   DIRECTS        -> W=1.0  (CEO, board director)
#   OWNS_MAJORITY  -> W=1.0  (>= 25% ownership)
#   OWNS_MINORITY  -> W=0.1  (< 25% ownership)
#   LOCATED_AT     -> W=0.1  (registered address / jurisdiction link)

BASELINE_COMPANIES: list[dict] = [

    # ── Wirecard AG ────────────────────────────────────────────────────────────
    # Classic accounting fraud: CEO Markus Braun arrested, COO Jan Marsalek fled.
    # Braun's arrest is public news → adverse_score should be high → contagion to Wirecard.
    {
        "legal_name": "Wirecard AG",
        "aliases": ["Wirecard"],
        "domain": "wirecard.com",
        "lei": "529900A8LX4KL0YUTH71",
        "country": "DE",
        "legal_form": "AG (Aktiengesellschaft)",
        "jurisdiction": "DE",
        "expected_business_model": "Licensed payment processing and merchant acquiring.",
        "expected_activity": "Card-payment settlement for European e-commerce merchants.",
        "expected_monthly_volume_eur": 250_000_000,
        "baseline_risk_rating": "MEDIUM",
        "onboarding_date": dt.date(2016, 1, 15),
        "notes": "DAX-listed payments group. Collapsed in 2020 due to EUR 1.9B accounting fraud.",
        "topology": [
            {"name": "Markus Braun",  "node_type": "PERSON", "role": "CEO / Executive Director",      "ownership_pct": 7.0,  "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Jan Marsalek",  "node_type": "PERSON", "role": "COO / Executive Director",      "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "James Freis",   "node_type": "PERSON", "role": "Interim CEO (post-fraud)",      "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "SoftBank Group","node_type": "COMPANY","role": "Strategic investor",            "ownership_pct": 5.6,  "rel_type": "OWNS_MINORITY", "control_weight": 0.1, "at_onboarding_risk": 0.1},
        ],
    },

    # ── FTX Trading Ltd ────────────────────────────────────────────────────────
    # SBF convicted of fraud; Caroline Ellison, Ryan Salame also charged.
    {
        "legal_name": "FTX Trading Ltd",
        "aliases": ["FTX", "FTX Exchange"],
        "domain": "ftx.com",
        "lei": None,
        "country": "BS",
        "legal_form": "Ltd (offshore)",
        "jurisdiction": "BS",
        "expected_business_model": "Centralised crypto-asset exchange and custody.",
        "expected_activity": "Spot and derivatives crypto trading for retail/institutional clients.",
        "expected_monthly_volume_eur": 500_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2021, 3, 1),
        "notes": "Offshore crypto exchange. Collapsed Nov 2022; founder SBF convicted of fraud.",
        "topology": [
            {"name": "Sam Bankman-Fried", "node_type": "PERSON", "role": "Founder & CEO",         "ownership_pct": 53.0, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Caroline Ellison",  "node_type": "PERSON", "role": "CEO of Alameda Research","ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Ryan Salame",       "node_type": "PERSON", "role": "Co-CEO FTX Digital Mkts","ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Sequoia Capital",   "node_type": "COMPANY","role": "Venture investor",       "ownership_pct": 1.0,  "rel_type": "OWNS_MINORITY", "control_weight": 0.1, "at_onboarding_risk": 0.2},
        ],
    },

    # ── MicroStrategy (now Strategy) ───────────────────────────────────────────
    # BEST semantic drift case: onboarded as BI software company, pivoted to
    # Bitcoin accumulation vehicle. Michael Saylor publicly associated with Bitcoin.
    {
        "legal_name": "MicroStrategy Incorporated",
        "aliases": ["MicroStrategy", "Strategy", "MSTR"],
        "domain": "microstrategy.com",
        "lei": None,
        "country": "US",
        "legal_form": "Form 10-K Corp",
        "jurisdiction": "US-VA",
        "expected_business_model": "Enterprise Business Intelligence software and cloud analytics.",
        "expected_activity": "B2B software licensing and cloud subscriptions to enterprise clients.",
        "expected_monthly_volume_eur": 5_000_000,
        "baseline_risk_rating": "LOW",
        "onboarding_date": dt.date(2020, 1, 10),
        "notes": (
            "Onboarded as BI software company. "
            "In Aug 2020 pivoted to Bitcoin treasury strategy; now holds >500k BTC. "
            "Classic semantic drift: software -> crypto asset holding company."
        ),
        "topology": [
            {"name": "Michael Saylor",  "node_type": "PERSON", "role": "Executive Chairman / Founder", "ownership_pct": 30.0, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Phong Le",        "node_type": "PERSON", "role": "CEO",                          "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Andrew Kang",     "node_type": "PERSON", "role": "CFO",                          "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Capital International Investors", "node_type": "COMPANY", "role": "Institutional shareholder", "ownership_pct": 11.2, "rel_type": "OWNS_MINORITY", "control_weight": 0.1, "at_onboarding_risk": 0.1},
        ],
    },

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    {
        "legal_name": "OpenAI",
        "aliases": ["OpenAI Inc", "OpenAI Global LLC"],
        "domain": "openai.com",
        "lei": None,
        "country": "US",
        "legal_form": "Capped-profit LLC",
        "jurisdiction": "US-CA",
        "expected_business_model": "AI research lab monetising via API and subscriptions.",
        "expected_activity": "B2B/B2C software subscriptions and cloud API revenue.",
        "expected_monthly_volume_eur": 80_000_000,
        "baseline_risk_rating": "LOW",
        "onboarding_date": dt.date(2023, 6, 1),
        "notes": "Fast-scaling AI company; watch for scale-risk and funding signals.",
        "topology": [
            {"name": "Sam Altman",      "node_type": "PERSON", "role": "CEO",             "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Greg Brockman",   "node_type": "PERSON", "role": "President",       "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Microsoft",       "node_type": "COMPANY","role": "Strategic investor","ownership_pct": 49.0, "rel_type": "OWNS_MAJORITY", "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Sequoia Capital",   "node_type": "COMPANY","role": "Early-stage investor", "ownership_pct": None, "rel_type": "OWNS_MINORITY", "control_weight": 0.1, "at_onboarding_risk": 0.2},
        ],
    },

    # ── VTB Bank ───────────────────────────────────────────────────────────────
    {
        "legal_name": "VTB Bank",
        "aliases": ["VTB Bank (PJSC)", "Bank VTB", "Vneshtorgbank", "VTB", "VTB BANK JSC"],
        "domain": "vtb.ru",
        "lei": None,
        "country": "RU",
        "legal_form": "PJSC (Public Joint Stock Company)",
        "jurisdiction": "RU",
        "expected_business_model": "State-owned commercial and investment bank.",
        "expected_activity": "Corporate lending, trade finance, capital markets, retail banking.",
        "expected_monthly_volume_eur": 1_000_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2019, 6, 1),
        "notes": "Russia's second-largest bank. Sanctioned by EU/OFAC/UK/AU/CA/CH (2022).",
        "topology": [
            {"name": "Andrei Kostin",    "node_type": "PERSON", "role": "President & Chairman",    "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Dmitry Pyanov",    "node_type": "PERSON", "role": "Deputy President",        "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Government of Russia", "node_type": "COMPANY", "role": "Majority shareholder", "ownership_pct": 61.8, "rel_type": "OWNS_MAJORITY", "control_weight": 1.0, "at_onboarding_risk": 0.15},
            {"name": "Gazprom",          "node_type": "COMPANY", "role": "Energy-sector counterparty", "ownership_pct": None, "rel_type": "ASSOCIATED_WITH", "control_weight": 0.1, "at_onboarding_risk": 0.2},
        ],
    },

    # ── Gazprombank ────────────────────────────────────────────────────────────
    {
        "legal_name": "Gazprombank",
        "aliases": ["Gazprombank JSC", "GPB", "Joint Stock Company Gazprombank"],
        "domain": "gazprombank.ru",
        "lei": None,
        "country": "RU",
        "legal_form": "JSC (Joint Stock Company)",
        "jurisdiction": "RU",
        "expected_business_model": "Large private/state-linked commercial bank.",
        "expected_activity": "Energy-sector financing, project finance, retail and corporate banking.",
        "expected_monthly_volume_eur": 800_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2019, 9, 1),
        "notes": "Major Russian bank tied to Gazprom. Sanctioned EU/OFAC/UK/AU/CA/CH.",
        "topology": [
            {"name": "Andrey Akimov",   "node_type": "PERSON", "role": "Chairman of Management Board", "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Gazprom",         "node_type": "COMPANY","role": "Majority shareholder",          "ownership_pct": 35.5, "rel_type": "OWNS_MAJORITY", "control_weight": 1.0, "at_onboarding_risk": 0.2},
            {"name": "Government of Russia", "node_type": "COMPANY", "role": "Sovereign / state nexus", "ownership_pct": None, "rel_type": "ASSOCIATED_WITH", "control_weight": 0.1, "at_onboarding_risk": 0.15},
        ],
    },

    # ── Surgutneftegas ─────────────────────────────────────────────────────────
    {
        "legal_name": "Surgutneftegas",
        "aliases": ["PJSC Surgutneftegas", "OAO Surgutneftegas", "Surgutneftegaz", "Surgut"],
        "domain": "surgutneftegas.ru",
        "lei": None,
        "country": "RU",
        "legal_form": "PJSC (Public Joint Stock Company)",
        "jurisdiction": "RU",
        "expected_business_model": "Vertically integrated Russian oil and gas producer.",
        "expected_activity": "Crude oil production, refining, and domestic retail fuel.",
        "expected_monthly_volume_eur": 500_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2020, 1, 15),
        "notes": "One of Russia's largest oil producers, opaque ownership. Sanctioned EU/AU/CA/UK/CH.",
        "topology": [
            {"name": "Vladimir Bogdanov", "node_type": "PERSON", "role": "CEO / General Director",  "ownership_pct": None, "rel_type": "DIRECTS",       "control_weight": 1.0, "at_onboarding_risk": 0.0},
            {"name": "Government of Russia", "node_type": "COMPANY", "role": "Sovereign / jurisdiction nexus", "ownership_pct": None, "rel_type": "ASSOCIATED_WITH", "control_weight": 0.1, "at_onboarding_risk": 0.15},
        ],
    },
]
