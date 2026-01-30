#!/usr/bin/env python3
"""
BEMIFY Batch Klimasimulering

Kjører BEMIFY-simuleringer for flere EPW-klimafiler automatisk.
Bruker BEMIFY's innebygde batchSimulateToNdjson som skriver direkte til fil.

Bruk:
    python bemify_batch_runner.py bygning.sxi ./klimafiler/ --headed

Krav:
    pip install playwright tqdm
    playwright install chromium
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
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


def kjor_batch_simulering(
    page: Page,
    sxi_innhold: str,
    epw_filer: list[tuple[str, str]],
    timeout_per_sim: int = 300_000,
) -> dict:
    """
    Kjør batch-simulering med BEMIFY's innebygde fil-streaming.
    Bruker batchSimulateToNdjson som åpner fil-dialog og skriver direkte til fil.
    """
    total_timeout = timeout_per_sim * len(epw_filer) + 60000
    page.set_default_timeout(total_timeout)
    
    # Parse SXI-fil
    print("[Runner] Parser SXI-fil...")
    sxi_escaped = escape_js_string(sxi_innhold)
    
    project_node = page.evaluate(f"""
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
    
    print(f"[Runner] Prosjekt: {project_node['name']}")
    print(f"[Runner] Kategori: {project_node['category']}, Soner: {project_node['zones']}")
    
    # Last ALLE klimafiler inn i nettleseren FØR simulering
    print(f"[Runner] Laster {len(epw_filer)} klimafiler inn i nettleseren...")
    
    for i, (navn, epw_innhold) in enumerate(epw_filer):
        epw_escaped = escape_js_string(epw_innhold)
        page.evaluate(f"""
            () => {{
                if (!window._climates) window._climates = [];
                const epwContent = `{epw_escaped}`;
                const {{ climateData }} = window.bemify.parseEpw(epwContent);
                window._climates.push({{ name: "{navn}", data: climateData }});
            }}
        """)
    
    print("[Runner] Alle klimafiler lastet")
    print("")
    print("=" * 60)
    print("VELG FIL-LOKASJON")
    print("=" * 60)
    print("En fil-dialog åpnes nå i nettleseren.")
    print("Velg hvor resultatene skal lagres (.ndjson)")
    print("=" * 60)
    print("")
    
    # Start batch-simulering
    page.evaluate("""
        () => {
            window._simProgress = { current: 0, total: 0, name: '' };
            window._simDone = false;
            window._simResult = null;
            window._simError = null;
            
            window.bemify.batchSimulateToNdjson(
                window._bemifyProject,
                window._climates,
                (completed, total, currentName) => {
                    window._simProgress = { current: completed, total, name: currentName };
                }
            ).then(result => {
                window._simResult = result;
                window._simDone = true;
            }).catch(err => {
                window._simError = err.message || String(err);
                window._simDone = true;
            });
        }
    """)
    
    # Poll for progress med progressbar
    total = len(epw_filer)
    pbar = tqdm(total=total, desc="Simulerer", unit="klima", ncols=60)
    last_completed = 0
    current_name = ""
    
    while True:
        time.sleep(0.3)
        
        status = page.evaluate("""
            () => ({
                done: window._simDone,
                progress: window._simProgress,
                result: window._simResult,
                error: window._simError
            })
        """)
        
        progress = status.get("progress", {})
        current = progress.get("current", 0)
        name = progress.get("name", "")
        
        if current > last_completed:
            pbar.update(current - last_completed)
            last_completed = current
        
        if name and name != current_name and name != "Ferdig":
            current_name = name
            pbar.set_description(f"Simulerer: {name}")
        
        if status.get("done"):
            pbar.update(total - last_completed)
            pbar.set_description("Simulerer")
            pbar.close()
            
            # Rydd opp
            page.evaluate("""
                () => {
                    delete window._climates;
                    delete window._bemifyProject;
                    delete window._simProgress;
                    delete window._simResult;
                    delete window._simDone;
                    delete window._simError;
                }
            """)
            
            if status.get("error"):
                print(f"[Runner] Feil: {status['error']}")
                return {"succeeded": [], "failed": [n for n, _ in epw_filer]}
            
            return status.get("result", {"succeeded": [], "failed": []})


def hent_auth_sti() -> Path:
    """Hent sti til lagret autentiseringstilstand."""
    return Path.home() / ".bemify_auth_state.json"


def logg_inn_og_lagre(playwright, bemify_url: str) -> Path:
    """Åpne nettleser for manuell innlogging, lagre autentiseringstilstand."""
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
    print(f"[Runner] Autentisering lagret")
    
    browser.close()
    return auth_sti


def main():
    parser = argparse.ArgumentParser(
        description="Kjør BEMIFY batch-simuleringer for flere klimafiler"
    )
    
    parser.add_argument("sxi_fil", type=Path, help="Sti til SIMIEN Pro .sxi-fil")
    parser.add_argument("epw_mappe", type=Path, help="Mappe med .epw-filer")
    parser.add_argument("--bemify-url", default="https://app.bemify.no", help="BEMIFY URL")
    parser.add_argument("--headed", action="store_true", help="Kjør nettleser synlig (PÅKREVD)")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per simulering i sekunder")
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
    
    if not args.headed:
        print("Feil: --headed er påkrevd (nettleseren må vise fil-dialogen)")
        sys.exit(1)
    
    print(f"Fant {len(epw_filer)} EPW-filer")
    print(f"Leser SXI-fil: {args.sxi_fil}")
    sxi_innhold = les_filinnhold(args.sxi_fil)
    
    print("Leser EPW-filer...")
    epw_data = []
    for epw_sti in epw_filer:
        navn = epw_sti.stem
        innhold = les_filinnhold(epw_sti)
        epw_data.append((navn, innhold))
        print(f"  Lastet: {navn}")
    
    auth_sti = hent_auth_sti()
    
    if args.relogin and auth_sti.exists():
        auth_sti.unlink()
        print("[Runner] Slettet lagret innlogging")
    
    print(f"\nStarter batch-simulering...")
    print(f"BEMIFY URL: {args.bemify_url}")
    print(f"Simuleringer: {len(epw_data)} klimafiler")
    print("-" * 60)
    
    start_tid = time.time()
    
    with sync_playwright() as p:
        if not auth_sti.exists():
            logg_inn_og_lagre(p, args.bemify_url)
        
        browser = p.chromium.launch(headless=False)
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
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(storage_state=str(auth_sti))
            page = context.new_page()
            page.goto(args.bemify_url, wait_until="networkidle", timeout=60000)
        
        print("[Runner] Venter på bemify API...")
        page.wait_for_function("typeof window.bemify !== 'undefined'", timeout=30000)
        print("[Runner] BEMIFY lastet")
        
        resultat = kjor_batch_simulering(page, sxi_innhold, epw_data, args.timeout * 1000)
        
        vellykket = len(resultat.get("succeeded", []))
        feilet = len(resultat.get("failed", []))
        
        if resultat.get("failed"):
            print(f"\nFeilede simuleringer: {', '.join(resultat['failed'])}")
        
        browser.close()
    
    tid_brukt = time.time() - start_tid
    print("-" * 60)
    print(f"Simulering fullført!")
    print(f"  Vellykket: {vellykket}/{len(epw_data)}")
    print(f"  Feilet: {feilet}")
    print(f"  Tid brukt: {tid_brukt:.1f}s")
    print(f"  Resultater lagret til valgt fil")


if __name__ == "__main__":
    main()
