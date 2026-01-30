# BEMIFY CLI Tools

Python-verktøy for å kjøre BEMIFY-simuleringer fra kommandolinjen.

## Oversikt

Disse scriptene lar deg automatisere BEMIFY-simuleringer, f.eks. for å kjøre samme bygningsmodell mot mange klimafiler. Nyttig for parameterstudier, klimasoneanalyser, eller validering mot andre verktøy.

**To tilnærminger:**

1. **Nettleserkonsoll** — Kjør direkte i browser via `bemify.*` API-et
2. **Python + Playwright** — Automatiser simuleringer fra kommandolinjen

## Forutsetninger

- Bruker på [app.bemify.no](https://app.bemify.no)
- Python 3.10+
- Bygningsmodell i SXI-format (SIMIEN Pro)
- Klimafiler i EPW-format

## Installasjon
```bash
pip install playwright pandas tqdm
playwright install chromium
```

## Bruk

### Alternativ 1: Direkte i nettleserkonsoll

1. Åpne [app.bemify.no](https://app.bemify.no) og logg inn
2. Åpne DevTools (F12) → Console
3. Skriv `bemify.help()` for å se tilgjengelige funksjoner

**Eksempel — enkel simulering:**
```javascript
const { climateData } = await bemify.loadEpw('http://localhost:8080/oslo.epw');
const project = await bemify.loadSxi('http://localhost:8080/bygning.sxi');
const result = await bemify.simulate(project, climateData);
bemify.downloadJson(result, 'resultat.json');
```

**Eksempel — batch-simulering:**
```javascript
const project = await bemify.loadSxi('http://localhost:8080/bygning.sxi');
const climates = [
  { name: 'Oslo', data: (await bemify.loadEpw('http://localhost:8080/oslo.epw')).climateData },
  { name: 'Bergen', data: (await bemify.loadEpw('http://localhost:8080/bergen.epw')).climateData },
];
const results = await bemify.batchSimulate(project, climates);
bemify.downloadJson(results, 'batch_resultat.json');
```

> **NB:** For å laste lokale filer trenger du en lokal HTTP-server med CORS. Se [Lokal server med CORS](#lokal-server-med-cors).

### Alternativ 2: Python-script med Playwright

For større batch-jobber eller automatisering.

**Kjør simuleringer:**
```bash
python bemify_batch_runner.py bygning.sxi ./klimafiler/ --headed
```

Scriptet:
1. Åpner BEMIFY i Chromium (krever innlogging første gang)
2. Laster SXI-modell og alle EPW-filer fra mappen
3. Kjører simuleringer og lagrer resultater til NDJSON-fil

**Analyser resultater:**
```bash
python bemify_results_analyzer.py results.ndjson
python bemify_results_analyzer.py results.ndjson -o summary.csv
```

## Lokal server med CORS

For å laste filer fra lokal disk via konsoll-API-et trenger du en HTTP-server som sender CORS-headers.

**One-liner (Python):**
```bash
python -c "from http.server import HTTPServer, SimpleHTTPRequestHandler; \
handler = type('H', (SimpleHTTPRequestHandler,), \
{'end_headers': lambda self: (self.send_header('Access-Control-Allow-Origin', '*'), \
SimpleHTTPRequestHandler.end_headers(self))}); \
HTTPServer(('', 8080), handler).serve_forever()"
```

Filene blir tilgjengelige på `http://localhost:8080/`.

## Filformater

### Input

| Format | Beskrivelse |
|--------|-------------|
| `.sxi` | SIMIEN Pro bygningsmodell |
| `.epw` | EnergyPlus Weather File |

### Output

**NDJSON** (Newline Delimited JSON) — én JSON-linje per simulering:
```json
{"climateName": "Oslo", "result": {...}}
{"climateName": "Bergen", "result": {...}}
```

Resultatene inneholder bl.a.:
- `stepResultsPerSone` — Effektbehov per tidssteg (35 040 kvartersintervaller)
- `varmetapstallPerSone` — Varmetapstall og arealer per sone

## Console API-referanse

| Funksjon | Beskrivelse |
|----------|-------------|
| `bemify.parseEpw(content)` | Parse EPW-streng → klimadata |
| `bemify.parseSxi(content)` | Parse SXI-streng → prosjekt |
| `bemify.loadEpw(url)` | Hent og parse EPW fra URL |
| `bemify.loadSxi(url)` | Hent og parse SXI fra URL |
| `bemify.simulate(project, climate)` | Kjør simulering |
| `bemify.batchSimulate(project, climates[])` | Batch-simulering, returnerer objekt |
| `bemify.batchSimulateToNdjson(project, climates[])` | Batch-simulering, streamer til fil |
| `bemify.downloadJson(data, filename)` | Last ned som JSON-fil |
| `bemify.help()` | Vis hjelpetekst |

## Lisens

MIT
