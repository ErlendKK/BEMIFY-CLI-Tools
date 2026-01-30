#!/usr/bin/env python3
"""
BEMIFY Results Analyzer - Kompakt versjon

Bruk:
    python bemify_results_analyzer.py results.ndjson
    python bemify_results_analyzer.py results.ndjson -o summary.csv
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("Feil: pandas ikke installert. Kjør: pip install pandas")
    sys.exit(1)

ENERGI_POSTER = [
    "1a Romoppvarming", "1b Ventilasjonsvarme", "2 Varmtvann",
    "3a Romkjøling", "3b Ventilasjonskjøling",
    "4a Vifter", "4b Pumper", "5 Belysning", "6 Teknisk utstyr",
]

TIMESTEP_HOURS = 0.25


def process_ndjson(filepath: Path) -> pd.DataFrame:
    """Les NDJSON og returner kompakt oppsummering."""
    rows = []
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            
            entry = json.loads(line)
            climate_name = entry.get("climateName", "Ukjent")
            result = entry.get("result", {})
            
            # Summer energi per post over alle soner og tidssteg
            energy_kwh = {post: 0.0 for post in ENERGI_POSTER}
            
            for step_list in result.get("stepResultsPerSone", {}).values():
                for step in step_list:
                    for post in ENERGI_POSTER:
                        power_w = step.get("effektBehov", {}).get(post, 0.0)
                        energy_kwh[post] += power_w * TIMESTEP_HOURS / 1000
            
            # Hent areal
            areal = sum(z.get("areal", 0) for z in result.get("varmetapstallPerSone", []))
            
            # Bygg kompakt rad
            total = sum(energy_kwh.values())
            rows.append({
                "Klimasted": climate_name,
                "Areal [m²]": areal,
                "Oppvarming": energy_kwh["1a Romoppvarming"] + energy_kwh["1b Ventilasjonsvarme"],
                "Varmtvann": energy_kwh["2 Varmtvann"],
                "Kjøling": energy_kwh["3a Romkjøling"] + energy_kwh["3b Ventilasjonskjøling"],
                "El-spesifikt": sum(energy_kwh[p] for p in ["4a Vifter", "4b Pumper", "5 Belysning", "6 Teknisk utstyr"]),
                "Sum [kWh]": total,
                "Sum [kWh/m²]": total / areal if areal > 0 else None,
            })
    
    return pd.DataFrame(rows).sort_values("Klimasted").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Analyser BEMIFY batch-resultater")
    parser.add_argument("ndjson_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Lagre til CSV")
    args = parser.parse_args()
    
    if not args.ndjson_file.exists():
        print(f"Feil: Finner ikke {args.ndjson_file}")
        sys.exit(1)
    
    df = process_ndjson(args.ndjson_file)
    
    print(f"\nEnergibehov per klimasted [kWh]")
    print("=" * 80)
    print(df.round(1).to_string(index=False))
    
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"\nLagret til: {args.output}")


if __name__ == "__main__":
    main()
