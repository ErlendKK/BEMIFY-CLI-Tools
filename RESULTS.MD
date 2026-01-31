# Resultatformat

Dokumentasjon av datastrukturen i BEMIFY simuleringsresultater.

## Overordnet struktur
```
SimulationResult
├── stepResultsPerSone     # Tidsseriedata per sone (35 040 tidssteg)
├── varmetapstallPerSone   # Varmetapstall og areal per sone
├── solcelleProduction     # Solcelleproduksjon per tidssteg
├── warnings               # Advarsler fra simuleringen
└── metadata               # Simuleringsmetadata
```

## Tidssteg

Simuleringen kjører med 15-minutters intervaller over ett år:

| Parameter | Verdi |
|-----------|-------|
| Tidssteg | 15 minutter (0,25 timer) |
| Tidssteg per år | 35 040 |
| Startdag | 1. januar (fredag) |

For å konvertere effekt [W] til energi [kWh]:
```python
energy_kWh = power_W * 0.25 / 1000
```

## stepResultsPerSone

Hovedresultatene ligger i `stepResultsPerSone` — et objekt hvor nøkkelen er sone-ID og verdien er en liste med 35 040 `StepData`-objekter.
```json
{
  "stepResultsPerSone": {
    "sone_abc123": [ StepData, StepData, ... ],
    "sone_def456": [ StepData, StepData, ... ]
  }
}
```

### StepData

Hvert tidssteg inneholder:

| Felt | Beskrivelse |
|------|-------------|
| `effektBehov` | Energibehov per post — beregningspunkt A |
| `termiskKildeYtelse` | Levert energi per kilde og kategori — beregningspunkt B/C |
| `distribusjonsOgAkkumuleringstap` | Tap i distribusjon og akkumulering |
| `inneklima` | Temperaturer, CO₂, fuktighet |
| `ventilasjon` | Luftmengder, temperaturer, virkningsgrader |

## Energiposter (Beregningspunkt A)

`effektBehov` angir sluttbrukers behov i watt [W], eksklusiv tap.

| Post | Beskrivelse |
|------|-------------|
| `1a Romoppvarming` | Oppvarming av rom |
| `1b Ventilasjonsvarme` | Oppvarming av ventilasjonsluft |
| `2 Varmtvann` | Tappevann |
| `3a Romkjøling` | Kjøling av rom |
| `3b Ventilasjonskjøling` | Kjøling av ventilasjonsluft |
| `4a Vifter` | Vifter i ventilasjonsanlegg |
| `4b Pumper` | Pumper i varme-/kjølesystem |
| `5 Belysning` | Belysning |
| `6 Teknisk utstyr` | Teknisk utstyr |
| `7 El-billading` | Elbil-lading |
| `8 Annet behov` | Andre behov |
| `9 Behov nærliggende bygg` | Energi levert til andre bygg |

**Eksempel — summere årlig energibehov:**
```python
annual_kWh = {}
for post in step_data[0]['effektBehov'].keys():
    total_W = sum(step['effektBehov'][post] for step in step_data)
    annual_kWh[post] = total_W * 0.25 / 1000
```

## Termisk kildeytelse (Beregningspunkt B/C)

`termiskKildeYtelse` viser hvordan energibehovet dekkes av ulike energibærere.

### Energibærere (EnergiLeveranse)

| Kode | Beskrivelse |
|------|-------------|
| `1 Levert elektrisitet` | Elektrisitet fra nett |
| `2a Fast biobrensel` | Ved, pellets, flis |
| `2b Flytende biobrensel` | Biodiesel, bioetanol |
| `2c Biobrensel i gassform` | Biogass |
| `2d Fast fossilt brensel` | Kull, koks |
| `2e Flytende fossilt brensel` | Olje, parafin |
| `2f Fossilt brensel i gassform` | Naturgass, propan |
| `3 Levert fjernvarme` | Fjernvarme |
| `4 Levert fjernkjøling` | Fjernkjøling |
| `5 Andre leverte energibærere` | Andre |
| `6 Egenprodusert elektrisitet til eksport (til fradrag)` | Solceller etc. |

### Struktur

For hver energibærer og termisk kategori:
```json
{
  "termiskKildeYtelse": {
    "1 Levert elektrisitet": {
      "1a Romoppvarming": {
        "input_W": 1500,
        "output_W": 4500,
        "tap_W": 100
      }
    },
    "3 Levert fjernvarme": {
      "1a Romoppvarming": {
        "input_W": 5000,
        "output_W": 4800,
        "tap_W": 200
      }
    }
  }
}
```

| Felt | Beskrivelse |
|------|-------------|
| `input_W` | Tilført energi fra energibærer (beregningspunkt C) |
| `output_W` | Levert energi til forbruker (beregningspunkt B) |
| `tap_W` | Tap i konvertering/distribusjon |

**Eksempel — beregne total levert elektrisitet:**
```python
total_el_input_W = 0
for step in step_data:
    el = step['termiskKildeYtelse'].get('1 Levert elektrisitet', {})
    for kategori, effekter in el.items():
        total_el_input_W += effekter.get('input_W', 0)

total_el_kWh = total_el_input_W * 0.25 / 1000
```

## Inneklima

`inneklima` inneholder beregnede inneklimaparametere for hvert tidssteg.

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `luftTemperatur` | °C | Romlufttemperatur (θ_i) |
| `overflateTemperatur` | °C | Indre overflatetemperatur (θ_s) |
| `masseTemperatur` | °C | Termisk massetemperatur (θ_m) |
| `operativTemperatur` | °C | Vektet snitt av luft og overflate (θ_op) |
| `tilluftsTemperatur` | °C | Tillufttemperatur |
| `tilluftsLuftmengde` | m³/h | Tilluftmengde |
| `CO2_nivå` | ppm | CO₂-konsentrasjon |
| `relativ_fuktighet` | % | Relativ fuktighet |
| `distribusjonsTap_rom` | — | Tap og tilskudd fra distribusjon |

## Ventilasjon

`ventilasjon` inneholder ventilasjonsdata for hvert tidssteg.

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `theta_sup` | °C | Faktisk tillufttemperatur |
| `theta_sup_setpoint` | °C | Tilluft-settpunkt |
| `RH_sup` | % | Relativ fuktighet i tilluft |
| `AH_sup` | g/kg | Absolutt fuktighet i tilluft |
| `V_TV` | m³/h | Tilluftmengde |
| `V_AV` | m³/h | Avtrekksmengde |
| `fanPower_W` | W | Vifteeffekt |
| `eta` | 0–1 | Varmegjenvinningsgrad |
| `batteriResultat` | — | Effekt fra varme-/kjølebatterier |

### batteriResultat

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `varme_lokal_W` | W | Effekt fra lokale/elektriske varmebatterier |
| `varme_sentral_W` | W | Effekt fra vannbårne varmebatterier |
| `kjøle_lokal_W` | W | Effekt fra lokale/elektriske kjølebatterier |
| `kjøle_sentral_W` | W | Effekt fra vannbårne kjølebatterier |
| `distribusjonstap_varme_W` | W | Tap i varmedistribusjon |
| `distribusjonstap_kjøle_W` | W | Tap i kjøledistribusjon |
| `tilskudd_W` | W | Tilskudd til sone (positiv=varme, negativ=kjøle) |

## varmetapstallPerSone

Statiske varmetapstall per sone.
```json
{
  "varmetapstallPerSone": [
    {
      "id": "sone_abc123",
      "areal": 250.5,
      "varmetapstall": {
        "yttervegger": 0.15,
        "yttertak": 0.08,
        "gulv": 0.05,
        "vinduer": 0.25,
        "kuldebroer": 0.06,
        "infiltrasjon": 0.04,
        "ventilasjon": 0.12
      }
    }
  ]
}
```

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `id` | — | Sone-ID |
| `areal` | m² | Oppvarmet bruksareal (BRA) |
| `varmetapstall.*` | W/(m²·K) | Varmetapstall per komponent |

## solcelleProduction

Solcelleproduksjon per tidssteg (35 040 elementer).

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `quarterOfYear` | — | Tidssteg-indeks (0–35039) |
| `powerOutput` | W | Produsert effekt |
| `cellTemperature` | °C | Celletemperatur |
| `I_sol` | W/m² | Solinnstråling på panel |
| `f_perf` | — | Total ytelsesfaktor |
| `IAM` | — | Incidence Angle Modifier |
| `phi_temp` | % | Temperaturtap |
| `phi_soil` | % | Tap pga. tilsmussing |

## metadata
```json
{
  "metadata": {
    "simulationTime": 12500,
    "totalSteps": 35040,
    "stepDuration": 0.25,
    "totalHours": 8760
  }
}
```

| Felt | Enhet | Beskrivelse |
|------|-------|-------------|
| `simulationTime` | ms | Beregningstid |
| `totalSteps` | — | Antall tidssteg |
| `stepDuration` | timer | Varighet per tidssteg |
| `totalHours` | timer | Simulert periode |

## warnings

Liste med advarsler generert under simuleringen.
```json
{
  "warnings": [
    {
      "type_": "warning",
      "message": "Varmepumpe opererer utenfor kapasitet",
      "zoneId": "sone_abc123",
      "method": "HeatPumpModel.calculate",
      "step": 15234,
      "log": "Detaljert feilmelding..."
    }
  ]
}
```

| Felt | Beskrivelse |
|------|-------------|
| `type_` | `info`, `message`, `warning`, `error`, `debug` |
| `message` | Kort beskrivelse |
| `zoneId` | Relevant sone (valgfri) |
| `method` | Metode som genererte advarselen (valgfri) |
| `step` | Tidssteg (valgfri) |
| `log` | Detaljert logg |
