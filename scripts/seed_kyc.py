"""Layer 2 - simulated internal KYC baseline profiles.

Each entry is a *fictional* baseline that represents what the bank believed at
onboarding. Layer 1 public signals are later compared against these assumptions
to detect KYC drift.

Companies are split into two groups:

Group A — high-profile case studies (no sanctions expected):
  Wirecard AG, FTX Trading Ltd, OpenAI

Group B — actively sanctioned entities (confirm sanctions collector works):
  VTB Bank, Gazprombank, Surgutneftegas
  All three appear in the OpenSanctions bulk dataset (EU, OFAC, AU, CA, CH, UK)
  and have registered LEIs in GLEIF.
"""
from __future__ import annotations

import datetime as dt

BASELINE_COMPANIES: list[dict] = [

    # ── Group A: case studies ────────────────────────────────────────────────

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
        "notes": "DAX-listed payments group. Collapsed in 2020 due to €1.9B accounting fraud.",
    },
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
    },
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
    },


    {
        "legal_name": "VTB Bank",
        "aliases": [
            "VTB Bank (PJSC)",
            "Bank VTB",
            "Vneshtorgbank",
            "VTB",
            "VTB BANK JSC",
        ],
        "domain": "vtb.ru",
        "lei": None,   # GLEIF will resolve by name
        "country": "RU",
        "legal_form": "PJSC (Public Joint Stock Company)",
        "jurisdiction": "RU",
        "expected_business_model": "State-owned commercial and investment bank.",
        "expected_activity": "Corporate lending, trade finance, capital markets, retail banking.",
        "expected_monthly_volume_eur": 1_000_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2019, 6, 1),
        "notes": (
            "Russia's second-largest bank, state-controlled. "
            "Sanctioned by EU, OFAC, UK, AU, CA, CH following the 2022 Ukraine invasion. "
            "Appears in OpenSanctions as 'VTB Bank'."
        ),
    },
    {
        "legal_name": "Gazprombank",
        "aliases": [
            "Gazprombank JSC",
            "GPB",
            "Joint Stock Company Gazprombank",
            "АО Газпромбанк",
        ],
        "domain": "gazprombank.ru",
        "lei": None,
        "country": "RU",
        "legal_form": "JSC (Joint Stock Company)",
        "jurisdiction": "RU",
        "expected_business_model": "Large private/state-linked commercial bank.",
        "expected_activity": (
            "Energy-sector financing, project finance for Gazprom group, "
            "retail and corporate banking."
        ),
        "expected_monthly_volume_eur": 800_000_000,
        "baseline_risk_rating": "HIGH",
        "onboarding_date": dt.date(2019, 9, 1),
        "notes": (
            "Major Russian bank closely tied to Gazprom. "
            "Sanctioned by EU, OFAC, UK, AU, CA, CH. "
            "Appears in OpenSanctions as 'Gazprombank'."
        ),
    },
    {
        "legal_name": "Surgutneftegas",
        "aliases": [
            "PJSC Surgutneftegas",
            "OAO Surgutneftegas",
            "Surgutneftegaz",
            "Surgut",
        ],
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
        "notes": (
            "One of Russia's largest oil producers, opaque ownership structure. "
            "Sanctioned by EU, AU, CA, UK, CH. "
            "Appears in OpenSanctions as 'Surgutneftegas'."
        ),
    },
]
