# BEMIFY CLI Tools

Verktøy for å kjøre BEMIFY-simuleringer fra kommandolinjen, nettleserkonsollen eller Python script.

## Oversikt

BEMIFY eksponerer et konsoll-API (`bemify.*`) som lar deg kjøre simuleringer, batch-simulere mot flere klimafiler, og laste ned resultater i to oppløsninger:

- **JSON** — kvartersoppløsning (35 040 tidssteg)
- **Excel** — timesoppløsning med ett ark per sone

Du trenger ingen ekstra installasjon for å bruke konsoll-API-et, bare åpne DevTools i nettleseren. For større batch-jobber finnes det Python-script med Playwright som automatiserer flyten.

## Forutsetninger

- Bruker på [app.bemify.no](https://app.bemify.no)
- Bygningsmodell i SXI-format (SIMIEN Pro)
- Klimafiler i EPW-format (kun nødvendig for batch-simulering — ellers brukes klimadata fra UI)

## Nettleserkonsoll (console API)

1. Åpne [app.bemify.no](https://app.bemify.no) og logg inn
2. Last inn prosjekt og klimadata som vanlig i UI
3. Åpne DevTools (F12) → Console
4. Skriv `bemify.help()` for å se tilgjengelige funksjoner

### Simuler og last ned

```javascript
// Bruker prosjekt og klimadata som allerede er lastet i UI.
bemify.simulate()
bemify.downloadExcel()   // Timesverdier — venter automatisk på simulering
bemify.downloadJson()    // Kvartersverdier — venter automatisk på simulering
```

### Excel med spesifikke kategorier

```javascript
bemify.simulate()
bemify.downloadExcel({ categories: ['effektBehov', 'inneklima'] })
```

### Eksplisitt med resultat-variabel

```javascript
const { climateData } = await bemify.loadEpw('http://localhost:8080/oslo.epw');
const project = await bemify.loadSxi('http://localhost:8080/bygning.sxi');
const result = await bemify.simulate(project, climateData);
bemify.downloadJson(result, 'resultat.json');
```

### Batch-simulering

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

### Console API-referanse

| Funksjon | Beskrivelse |
|----------|-------------|
| `bemify.simulate()` | Kjør simulering med data fra UI |
| `bemify.simulate(project, climate)` | Kjør simulering med eksplisitt data |
| `bemify.batchSimulate(project, climates[])` | Batch-simulering, returnerer objekt |
| `bemify.batchSimulateToNdjson(project, climates[])` | Batch-simulering, streamer til fil |
| `bemify.downloadExcel()` | Last ned siste resultat som Excel (timesverdier) |
| `bemify.downloadExcel(result, options?)` | Last ned spesifikt resultat som Excel |
| `bemify.downloadJson()` | Last ned siste resultat som JSON (kvartersverdier) |
| `bemify.downloadJson(data, filename?)` | Last ned data som JSON-fil |
| `bemify.parseEpw(content)` | Parse EPW-streng → klimadata |
| `bemify.parseSxi(content)` | Parse SXI-streng → prosjekt |
| `bemify.loadEpw(url)` | Hent og parse EPW fra URL |
| `bemify.loadSxi(url)` | Hent og parse SXI fra URL |
| `bemify.help()` | Vis hjelpetekst |

> `downloadExcel()` og `downloadJson()` venter automatisk på at en pågående simulering blir ferdig når de kalles uten argumenter.

### Excel-eksport kategorier

| Kategori | Beskrivelse |
|----------|-------------|
| `effektBehov` | Netto effektbehov per energipost [W] |
| `ventilasjon` | Tilluftstemperatur, luftmengder, vifteeffekt m.m. |
| `inneklima` | Temperaturer, CO₂, luftfuktighet m.m. |
| `distribusjonsOgAkkumuleringstap` | Tap for romoppvarming, ventilasjon, varmtvann, kjøling |
| `termiskKildeYtelse` | Input, output og tap per energibærer og kategori [W] |

## Python-script med Playwright

For større batch-jobber eller full automatisering uten manuell innlogging.

### Installasjon

```bash
pip install playwright pandas tqdm
playwright install chromium
```

### Kjør simuleringer

```bash
python bemify_batch_runner.py bygning.sxi ./klimafiler/ --headed
```

Scriptet:
1. Åpner BEMIFY i Chromium (krever innlogging første gang)
2. Laster SXI-modell og alle EPW-filer fra mappen
3. Kjører simuleringer og lagrer resultater til NDJSON-fil

### Analyser resultater

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

| Format | Oppløsning | Beskrivelse |
|--------|------------|-------------|
| JSON | 15 min (35 040 steg) | Komplett simuleringsresultat |
| Excel | 1 time (8 760 steg) | Ett ark per sone + aggregert «Samlet»-ark |
| NDJSON | 15 min (35 040 steg) | Batch-resultater, én JSON-linje per simulering |

**NDJSON-eksempel:**
```json
{"climateName": "Oslo", "result": {...}}
{"climateName": "Bergen", "result": {...}}
```

## Output-innhold

Resultatene inneholder bl.a.:
- `effektBehov` — Energibehov per post (beregningspunkt A)
- `termiskKildeYtelse` — Levert energi per kilde (beregningspunkt B/C)
- `inneklima` — Temperaturer, CO₂, fuktighet
- `ventilasjon` — Luftmengder, virkningsgrader

Se [RESULTS.md](RESULTS.md) for komplett beskrivelse av datastrukturen.

## Lisens

MIT
