#!/usr/bin/env python3
"""
BEMIFY Compact Batch Runner

Kjører BEMIFY-simuleringer for flere EPW-klimafiler og returnerer kun
3 nøkkeltall per klimasted (designet for NMBUs klimasammenligning):

  - Timer med lufttemperatur over 26 °C
  - Årlig varmeenergi (netto, 1a + 1b) [kWh]
  - Årlig kjøleenergi (netto, 3a + 3b) [kWh]

Bruk:
    python bemify_compact_runner.py bygning.sxi ./klimafiler/ --headed
    python bemify_compact_runner.py bygning.sxi ./klimafiler/ --headed -o resultater.csv

Krav:
    pip install playwright tqdm
    playwright install chromium
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    print("Feil: playwright er ikke installert. Kjør:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Feil: tqdm er ikke installert. Kjør:")
    print("  pip install tqdm")
    sys.exit(1)


def hent_epw_location(innhold: str) -> str | None:
    """Hent LOCATION-felt fra EPW-header (første kommaseparerte felt etter 'LOCATION,')."""
    for line in innhold.splitlines():
        if line.startswith("LOCATION,"):
            parts = line.split(",")
            if len(parts) >= 2 and parts[1].strip():
                return parts[1].strip()
    return None


def finn_epw_filer(mappe: Path) -> list[Path]:
    """Finn alle .epw-filer i mappen."""
    epw_filer = sorted(mappe.glob("*.epw"))
    if not epw_filer:
        epw_filer = sorted(mappe.glob("**/*.epw"))
    return epw_filer


def les_filinnhold(filsti: Path) -> str:
    """Les filinnhold som tekst."""
    with open(filsti, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def escape_js_string(s: str) -> str:
    """Escape streng for JavaScript template literal."""
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def kjor_compact_batch(
    page: Page,
    sxi_innhold: str,
    epw_filer: list[tuple[str, str]],
    timeout_per_sim: int = 300_000,
) -> dict:
    """
    Kjør kompakt batch-simulering via bemify.batchSimulateCompact.
    Returnerer kun 3 nøkkeltall per klimasted.
    """
    total_timeout = timeout_per_sim * len(epw_filer) + 60_000
    page.set_default_timeout(total_timeout)

    # Parse SXI
    print("[Runner] Parser SXI-fil...")
    sxi_escaped = escape_js_string(sxi_innhold)

    project_info = page.evaluate(f"""
        async () => {{
            const sxiContent = `{sxi_escaped}`;
            const projectNode = await window.bemify.parseSxi(sxiContent);
            window._bemifyProject = projectNode;
            return {{
                name: projectNode.data.navn,
                category: projectNode.data.bygningskategori,
                zones: projectNode.children?.filter(c => c.type === 'sone')?.length || 0
            }};
        }}
    """)

    print(f"[Runner] Prosjekt: {project_info['name']}")
    print(f"[Runner] Kategori: {project_info['category']}, Soner: {project_info['zones']}")

    # Last alle klimafiler
    print(f"[Runner] Laster {len(epw_filer)} klimafiler...")
    for navn, epw_innhold in epw_filer:
        epw_escaped = escape_js_string(epw_innhold)
        navn_escaped = navn.replace("\\", "\\\\").replace('"', '\\"')
        page.evaluate(f"""
            () => {{
                if (!window._climates) window._climates = [];
                const epwContent = `{epw_escaped}`;
                const {{ climateData }} = window.bemify.parseEpw(epwContent);
                window._climates.push({{ name: "{navn_escaped}", data: climateData }});
            }}
        """)

    print("[Runner] Alle klimafiler lastet")

    # Run simulations one at a time, extracting compact summary in JS
    total = len(epw_filer)
    compact_results = []

    pbar = tqdm(total=total, unit="klima", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} {postfix}")

    for i in range(total):
        # Start simulation i and poll until done
        page.evaluate(f"""
            () => {{
                window._simDone = false;
                window._simResult = null;
                window._simError = null;

                const climate = window._climates[{i}];
                window.bemify.simulate(window._bemifyProject, climate.data)
                    .then(result => {{
                        // Extract compact summary in-browser
                        let stepsOver26 = 0;
                        let varme = 0;
                        let kjole = 0;
                        for (const steps of Object.values(result.stepResultsPerSone)) {{
                            for (const s of steps) {{
                                if (s.inneklima.luftTemperatur > 26) stepsOver26++;
                                varme += (s.effektBehov['1a Romoppvarming'] || 0)
                                       + (s.effektBehov['1b Ventilasjonsvarme'] || 0);
                                kjole += (s.effektBehov['3a Romkjøling'] || 0)
                                       + (s.effektBehov['3b Ventilasjonskjøling'] || 0);
                            }}
                        }}
                        window._simResult = {{
                            climateName: climate.name,
                            timerOver26: stepsOver26 * 0.25,
                            varmeenergi_kWh: varme * 0.25 / 1000,
                            kjoleenergi_kWh: kjole * 0.25 / 1000,
                        }};
                        window._simDone = true;
                    }})
                    .catch(err => {{
                        window._simError = err.message || String(err);
                        window._simDone = true;
                    }});
            }}
        """)

        # Poll until this simulation finishes
        while True:
            time.sleep(0.5)
            status = page.evaluate("""
                () => ({
                    done: window._simDone,
                    result: window._simResult,
                    error: window._simError
                })
            """)
            if status.get("done"):
                break

        if status.get("error"):
            print(f"\n[Runner] Feil for klima {i+1}: {status['error']}")
        elif status.get("result"):
            compact_results.append(status["result"])
            r = status["result"]
            pbar.set_postfix_str(r['climateName'])

        pbar.update(1)

    pbar.close()

    # Clean up
    page.evaluate("""
        () => {
            delete window._climates;
            delete window._bemifyProject;
            delete window._simDone;
            delete window._simResult;
            delete window._simError;
        }
    """)

    return {
        "model": project_info["name"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_simulations": len(compact_results),
        "results": compact_results,
    }


def hent_auth_sti() -> Path:
    return Path.home() / ".bemify_auth_state.json"


def logg_inn_og_lagre(playwright, bemify_url: str) -> Path:
    auth_sti = hent_auth_sti()

    print("\n" + "=" * 60)
    print("INNLOGGING KREVES")
    print("=" * 60)
    print("En nettleser åpnes nå. Vennligst logg inn på BEMIFY.")
    print("Når du er logget inn, trykk ENTER her for å fortsette...")
    print("=" * 60 + "\n")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(bemify_url, wait_until="networkidle", timeout=60000)

    input("Trykk ENTER når du er logget inn...")

    context.storage_state(path=str(auth_sti))
    print("[Runner] Autentisering lagret")
    browser.close()
    return auth_sti


def skriv_resultater(result: dict, output_path: Path | None):
    """Skriv resultater til konsoll og evt. CSV."""
    results = result.get("results", [])
    model = result.get("model", "Ukjent")

    print(f"\n{'=' * 78}")
    print(f"  Resultater for: {model}")
    print(f"  {result.get('n_simulations', 0)} simuleringer")
    print(f"{'=' * 78}")
    print(f"  {'Klimasted':<30} {'Timer >26°C':>12} {'Varme [kWh]':>14} {'Kjøle [kWh]':>14}")
    print(f"  {'-' * 72}")

    for r in results:
        print(
            f"  {r['climateName']:<30} "
            f"{r['timerOver26']:>12.1f} "
            f"{r['varmeenergi_kWh']:>14.1f} "
            f"{r['kjoleenergi_kWh']:>14.1f}"
        )

    if output_path:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["climateName", "timerOver26", "varmeenergi_kWh", "kjoleenergi_kWh"],
            )
            writer.writeheader()
            writer.writerows(results)
        print(f"\nLagret til: {output_path}")

    # Lagre JSON også
    json_path = (output_path or Path("results.csv")).with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"JSON lagret til: {json_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Kjør BEMIFY batch-simulering (3 nøkkeltall per klimasted)"
    )
    parser.add_argument("sxi_fil", type=Path, help="Sti til SIMIEN Pro .sxi-fil")
    parser.add_argument("epw_mappe", type=Path, help="Mappe med .epw-filer")
    parser.add_argument("-o", "--output", type=Path, help="Lagre resultater til CSV")
    parser.add_argument("--bemify-url", default="https://app.bemify.no", help="BEMIFY URL")
    parser.add_argument("--headed", action="store_true", help="Kjør nettleser synlig")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per sim (sekunder)")
    parser.add_argument("--relogin", action="store_true", help="Logg inn på nytt")

    args = parser.parse_args()

    if not args.sxi_fil.exists():
        print(f"Feil: Finner ikke SXI-fil: {args.sxi_fil}")
        sys.exit(1)

    if not args.epw_mappe.exists():
        print(f"Feil: Finner ikke EPW-mappe: {args.epw_mappe}")
        sys.exit(1)

    epw_filer = finn_epw_filer(args.epw_mappe)
    if not epw_filer:
        print(f"Feil: Ingen .epw-filer funnet i {args.epw_mappe}")
        sys.exit(1)

    print(f"Fant {len(epw_filer)} EPW-filer")
    print(f"Leser SXI-fil: {args.sxi_fil}")
    sxi_innhold = les_filinnhold(args.sxi_fil)

    print("Leser EPW-filer...")
    epw_data = []
    for epw_sti in epw_filer:
        innhold = les_filinnhold(epw_sti)
        navn = hent_epw_location(innhold) or epw_sti.stem
        epw_data.append((navn, innhold))
        print(f"  {epw_sti.name} -> {navn}")

    auth_sti = hent_auth_sti()
    if args.relogin and auth_sti.exists():
        auth_sti.unlink()
        print("[Runner] Slettet lagret innlogging")

    print(f"\nStarter kompakt batch-simulering...")
    print(f"  BEMIFY URL: {args.bemify_url}")
    print(f"  Simuleringer: {len(epw_data)} klimafiler")
    print(f"  Output: timer >26°C, varmeenergi, kjøleenergi")
    print("-" * 60)

    start_tid = time.time()

    with sync_playwright() as p:
        if not auth_sti.exists():
            logg_inn_og_lagre(p, args.bemify_url)

        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(storage_state=str(auth_sti))
        page = context.new_page()

        print(f"[Runner] Laster BEMIFY fra {args.bemify_url}...")
        page.goto(args.bemify_url, wait_until="networkidle", timeout=60000)

        if "login" in page.url.lower() or "auth" in page.url.lower():
            print("[Runner] Sesjonen har utløpt...")
            browser.close()
            if auth_sti.exists():
                auth_sti.unlink()
            logg_inn_og_lagre(p, args.bemify_url)
            browser = p.chromium.launch(headless=not args.headed)
            context = browser.new_context(storage_state=str(auth_sti))
            page = context.new_page()
            page.goto(args.bemify_url, wait_until="networkidle", timeout=60000)

        print("[Runner] Venter på bemify API...")
        page.wait_for_function("typeof window.bemify !== 'undefined'", timeout=30000)
        print("[Runner] BEMIFY lastet")

        result = kjor_compact_batch(page, sxi_innhold, epw_data, args.timeout * 1000)

        browser.close()

    tid_brukt = time.time() - start_tid

    if result:
        skriv_resultater(result, args.output)

    print(f"\nTid brukt: {tid_brukt:.1f}s")


if __name__ == "__main__":
    main()