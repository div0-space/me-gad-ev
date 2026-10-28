---
source: sesja unicode-codescribe-megadev (Klaudiusz) + MCP mega-challenge
trust: zweryfikowane-w-MCP (statusy challenge'ów), relacja (statusy briefów lekcji sprzed 28.10)
stan-na: 2026-10-28
maintainer: wspólnie — Maciej + agenci; aktualizuj przy każdej zmianie statusu
---

# MATRIX — zadania MEGA.dev od A do Z

Jedna tabela prawdy o każdym zadaniu kursu. Status zmienia TYLKO ten, kto ma dowód
(wpis w logu, odpowiedź MCP, artefakt). Wpadki liniowane w journalu, nie ukrywane.

## Zadania

| Zadanie | Typ | Status | Wykonawca / run | Artefakty | Journal |
| --- | --- | --- | --- | --- | --- |
| Lekcja s01e01 | brief dnia | nieznany (do sprawdzenia na dashboardzie) | — | — | — |
| Lekcja s01e02 | brief dnia | nieznany (do sprawdzenia na dashboardzie) | — | — | — |
| Lekcja s01e03 „Building Knowledge Systems" | brief dnia | **zapisany** (2026-10-28, save-brief; 1 retry po HTTP 500) | Klaudiusz | dashboard hq.mega.dev | wpis #1 |
| Assessment | profil studenta | **niezrobiony** (mega-start: brief pisany bez niego) | Maciej + agent | — | — |
| Challenge S01E01 „somebody slow" | live | **brief gotowy, czeka na dispatch Macieja** | omp / gpt-6.1-sol | `challenges/S01E01/` | — |
| Challenge S01E02 „who said what" | live | **brief gotowy, czeka na dispatch Macieja** | omp / gpt-6.1-sol | `challenges/S01E02/` | — |
| Challenge S01E03 „what it shows" | live | **brief gotowy, czeka na dispatch Macieja** | omp / gpt-6.1-sol | `challenges/S01E03/` | — |
| Bench P1 (replika S01E01) | offline 9 modeli | zablokowany do rozwiązania S01E01 | flota | `bench/` | — |
| Bench P2 (replika S01E02) | offline 9 modeli | zablokowany do rozwiązania S01E02 | flota | `bench/` | — |

## Zasady statusów

- `nieznany` — nikt nie sprawdził; nie zgadujemy.
- `brief gotowy` — plik `challenges/<CODE>/brief.md` istnieje; dispatch to decyzja Macieja
  (worker: omp, model gpt-6.1-sol, mega MCP zalogowany na harnessie omp).
- `solved` wpisujemy wyłącznie po `claim`/`debrief` potwierdzonym przez MCP — nie po
  deklaracji workera.
- Każde zamknięte zadanie MUSI mieć: `log.md` (surowy zapis), `debrief.md`,
  `journal-entry.md` (narracja z wpadkami) — bez kompletu status najwyżej „solved bez
  dokumentacji" i to jest dług.

## Proponowane komendy dispatchu (decyzja i wykonanie: Maciej)

```bash
vibecrafted justdo omp --model gpt-6.1-sol --repo /Volumes/vc-workspace/vetcoders/me-gad-ev --file challenges/S01E01/brief.md
vibecrafted justdo omp --model gpt-6.1-sol --repo /Volumes/vc-workspace/vetcoders/me-gad-ev --file challenges/S01E02/brief.md
vibecrafted justdo omp --model gpt-6.1-sol --repo /Volumes/vc-workspace/vetcoders/me-gad-ev --file challenges/S01E03/brief.md
```

Uwaga: briefy zakładają Living Tree (bez `--worktree`), bo logi i artefakty mają lądować
wprost w `challenges/<CODE>/`; foldery trzech workerów są rozłączne, commity tylko we
własnym folderze.
