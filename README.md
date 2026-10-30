# me·gad·ev / The Journal

Dziennik Macieja Gada z pracy z agentami: plany, dispatch, decyzje i wyniki kolejnych
zadań. `me·gad·ev` to osobisty znak projektu; **The Journal** to tytuł publikacji.

English is the default at `/`; Polish is available under `/pl/`. The EN/PL
switch preserves the current page or story.

## Źródła i wynik publikacji

| Ścieżka | Zawartość |
| --- | --- |
| `content/posts.json` | Publiczne wpisy, obie wersje językowe |
| `content/site-copy.json` | Autorskie strony: główna, odcinki, warsztat i bramka, PL/EN |
| `.vibecrafted/content/member-posts.json` | Prywatne źródło własnych wpisów dla uczestników; ignorowane przez Git |
| `tools/build_journal.py` | Wspólny wydawca stron, archiwów, wpisów, RSS i indeksu dla agentów |
| `tools/build_og.py` | Karta Open Graph z oryginalnym emblematem i glifami Art API |
| `docs/` | Wyłącznie publiczny wynik publikacji i współdzielone zasoby |
| `server/` | Serwer ćwiczeniowy, bramka dostępu i lokalny podgląd |
| `bench/` | Materiały dotyczące porównania wykonawców |

Wpisy używają schematu `me-gad-ev.journal.v2`: stała tożsamość i daty wpisu,
osobne `translations.pl` i `translations.en`. Strony używają
`me-gad-ev.site.v1`. HTML w źródłach jest zaufanym materiałem redakcyjnym,
nie treścią przyjmowaną od odwiedzających.

Nowość wpisu wyznaczają `published`, `sequence` i `id`, malejąco.
Zmiana `updated` nie przesuwa starego wpisu na początek archiwum.

## Dwa poziomy dostępu

| Wersja | Publiczna | Dla uczestników |
| --- | --- | --- |
| EN · default | `/journal/` | `/members/journal/` |
| PL | `/pl/journal/` | `/members/pl/journal/` |

Publiczna opowieść opisuje naszą pracę bez instrukcji i rozwiązań kursu.
Szczegółowe własne relacje pozostają za bramką. Prywatny wynik publikacji musi
znajdować się **poza checkoutem**, nigdy w `docs/`. Obie wersje członkowskie
pozostają pod `/members/*`, za tym samym sprawdzeniem dostępu.

Człowiek loguje się przez oficjalne MEGA.dev; agent może przeprowadzić go przez
ten sam proces. Backend sprawdza dostęp świeżym OAuth, a nie deklaracją agenta.
Konfiguracja i obsługa tokenów: [`server/README.md`](server/README.md).
Trzy stare kopie dosłownych instrukcji `/challenge/s01e0X/entry/` są wycofane
z serwowania (410), bez usuwania prywatnych plików źródłowych. Zapis na kurs
nie daje nam zgody na redystrybucję jego instrukcji.

## Publikowanie

```sh
python3 tools/build_journal.py \
  --site-source content/site-copy.json \
  --public-source content/posts.json --public-output docs

# Dodatkowo własne wpisy dla uczestników, do zewnętrznego katalogu:
python3 tools/build_journal.py \
  --site-source content/site-copy.json \
  --public-source content/posts.json --public-output docs \
  --private-source .vibecrafted/content/member-posts.json \
  --private-output /absolute/private/candidate
```

Wydawca sprawdza kompletność tłumaczeń, odbiorców i wszystkie docelowe ścieżki
przed zapisem. Nie dopuszcza przenikania korzeni publicznego i prywatnego.
Kanały RSS i publiczne metadane zawierają tylko publiczną redakcję.

Prywatną publikację przygotowuj w nowym katalogu wynikowym, aby usunięte wpisy
nie pozostały na serwerze. Oryginalne chronione materiały kursu zachowuj oddzielnie.
Sam build nie wdraża strony, nie uruchamia zadań kursu i nie restartuje usług.

### Podgląd lokalny

Konfiguracja własnego klienta OAuth i zewnętrznego katalogu prywatnego znajduje się
w ignorowanym `.vibecrafted/preview-main.env` z uprawnieniami `0600`.
Nie kopiuj do niego danych logowania z harnessu. Obecny podgląd korzysta z klienta
zarejestrowanego dla `http://127.0.0.1:18745/gate/callback`.

```sh
uv run --no-project --offline --env-file .vibecrafted/preview-main.env \
  server/.venv/bin/python -m uvicorn server.preview:create_preview \
  --factory --host 127.0.0.1 --port 18745 --no-access-log
```

Podgląd: <http://127.0.0.1:18745/> i <http://127.0.0.1:18745/pl/>.
Wyłączony access log chroni kody powrotu OAuth przed zapisaniem w logu żądań.
Zmiany statycznej witryny nie wymagają restartu produkcyjnego serwera ćwiczeniowego.

### Privacy and rights

The independent-journal disclaimer and privacy link are shared by all EN/PL pages.
`/privacy/` and `/pl/privacy/` name the controller, Maciej Gad (`void@div0.space`),
and explain optional verification, transient token processing, cookies and data rights.
Routine domain access logging is disabled in production; the backend also uses
`--no-access-log`. Historical domain access logs were removed with owner approval.
Infrastructure error logs are separate; do not promise that no network data can
ever appear in diagnostics. Organizer approval and international-transfer details
have not been verified: do not promote the gate as an approved course integration.
See [`NOTICE`](NOTICE): this change does not relicense existing work or grant
rights to third-party course content, marks or story material.

### Manual verification

Ruff 0.14.14 uses the rules in `server/pyproject.toml`; the command checks both
Python source directories. These checks are manual, not an existing CI workflow
or a `make test-all` target.

```sh
ruff check --config server/pyproject.toml server tools
python3 -m unittest discover -s tools -p test_build_journal.py -v
uv run --project server python server/selftest.py
```

## Typografia i Art API

Nagłówki i znak projektu: **Monaspace Xenon**. Tekst: **Monaspace Neon**.
Departure Mono pozostaje wyłącznie małym akcentem `DEVLOG`, nie krojem nagłówków
ani znaku projektu. Fonty są lokalne; licencje pozostają przy plikach.

Departure Mono 1.500 autorstwa Heleny Zhang: `docs/assets/DepartureMono-1.500.woff2`,
SIL OFL 1.1, licencja `docs/assets/DepartureMono-LICENSE.txt`,
[źródło](https://github.com/rektdeckard/departure-mono/tree/75152a3f1e6dacdd248a6c397c97dbf27e33eea0/public/assets).

```sh
# Walidacja istniejących ilustracji, bez połączenia z API:
python3 tools/build_art.py --output docs/assets/art

# Świadome odświeżenie przez własne Art API:
ART_API_BASE=https://your-private-art-host.example \
  ART_API_KEY_FILE=/absolute/private/art-api-key \
  python3 tools/build_art.py --refresh --output docs/assets/art
```

Ilustracje łączą autorską geometrię z rzeczywistymi odpowiedziami Art API.
Manifest zapisuje ich hashe. Zwykła publikacja i czytanie nie wymagają API;
klucz ani prywatne wejścia nie należą do Git.

Karta Open Graph ma 1200 × 630 px. Publiczne strony używają
`/assets/art/journal-og.png`; strony członkowskie nie eksportują prywatnych
tytułów, opisów ani obrazów do metadanych społecznościowych.

```sh
# Odtworzenie karty z zapisanych, publicznych odpowiedzi API:
python3 tools/build_og.py

# Dwie nowe, uwierzytelnione operacje własnego Art API:
ART_API_BASE=https://your-private-art-host.example \
  ART_API_KEY_FILE=/absolute/private/art-api-key \
  python3 tools/build_og.py --refresh
```

Rasteryzacja wymaga zainstalowanego Chromium lub Chrome; opcja `--chromium`
wskazuje binarkę. Wydawca niczego nie instaluje. Karta osadza istniejący
`masthead.svg` bez zmian; manifest zawiera hashe źródeł i bezpieczne odpowiedzi
API. Jest autorską kompozycją, nie obrazem wygenerowanym przez model graficzny.

Pod znakiem projektu, w lewym dolnym rogu, widnieje drobny, dyskretny podpis
**made by × The VC Agents**: [VC](https://vetcoders.io),
[Agents](https://vibecrafted.io). To podpis zespołu i współpracy, nie przeniesienie
praw ani zastąpienie autorstwa tekstów. Obowiązują istniejąca [`LICENSE`](LICENSE), stopka
autorska oraz osobne licencje fontów. Dostęp do kursu nie jest zgodą na
redystrybucję jego materiałów: publikujemy własną redakcję, nie kopie zadań.

## Warsztat i pomiary

Jedna komórka formacji dispatchowej to jeden plan, jeden operator i jego flota.
Liczba planów jest zmienna; porównanie obejmuje dziewięć konfiguracji modeli.
Formacja 6 × 9 opisuje 54 komórki, nie liczbę udowodnionych ukończeń.
Pierwszą integrację tej strony przygotowały cztery workery i integrator;
korekta języków i identyfikacji powstaje w głównym checkoutcie.

Datowany stan z oficjalnego MCP, 2026-10-30: **S01E01–S01E04 rozwiązane**;
**S01E05 rozpoczęte, jeszcze nierozwiązane**. To zapis historyczny, nie panel
stanu na żywo. Pięć publicznych wpisów jest dostępnych w PL i EN, najnowszy
na początku. Metryka publiczna: [`MATRIX.md`](MATRIX.md).
The Journal jest publikacją uczestnika, nie oficjalnym wydawnictwem kursu.

Weryfikacja dostępu do Journal i prywatny MCP to odrębne mechanizmy.
Journal sprawdza uczestnictwo przez oficjalny OAuth. Nasz MCP jest wyłącznie
dla zespołu i flot agentów: używa prywatnego tokenu Bearer, bez logowania OAuth.
Brak lub błędny token daje `401` z informacją `private_mcp` i opisem nagłówka.
Token mocka nie daje dostępu do prawdziwego kursu; wykonawcy nadal nie powinni
mieć włączonego oficjalnego MCP. Konfiguracja: [`server/README.md`](server/README.md).

---

𝚅𝚒𝚋𝚎𝚌𝚛𝚊𝚏𝚝𝚎𝚍. with AI Agents by Vetcoders (c)2024-2026 LibraxisAI
