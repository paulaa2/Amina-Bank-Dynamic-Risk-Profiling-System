"""Search the OpenSanctions bulk CSV for well-known companies with public domains."""
import csv
import sys

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))

TARGETS = [
    "sberbank", "rosneft", "gazprom", "vtb bank", "novatek",
    "lukoil", "transneft", "sovcomflot", "nordstream", "nord stream",
    "bank rossiya", "bank russia", "surgutneftegas", "russian national",
]

VALID_SCHEMAS = {"Organization", "Company", "LegalEntity"}

with open("data/opensanctions_targets.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        if row.get("schema") not in VALID_SCHEMAS:
            continue
        name = row.get("name", "").lower()
        for t in TARGETS:
            if t in name:
                print(
                    f"schema={row['schema']:12} | name={row['name'][:60]:60} | "
                    f"countries={row['countries'][:6]:6} | "
                    f"datasets={row['dataset'][:55]}"
                )
                break
