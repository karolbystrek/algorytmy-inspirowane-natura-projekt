# Architektura rozwiązania

## Stan bieżący i docelowy

**Zaimplementowane w pilotażu:** przygotowanie OSM, wersjonowany kontrakt plików, model i trzy heurystyki, pełny przegląd, runner eksperymentów, wykresy/mapa statyczna, testy i CI.
**Planowane do 4 grudnia:** audyt wejść i kandydatów, lokalne poprawki danych, scenariusze docelowe, interfejs TypeScript/MapLibre z trasami i budynkami 3D. FastAPI pozostaje opcjonalne.

## Kontekst

```mermaid
flowchart LR
    OSM[OpenStreetMap przez Overpass] --> PREP[Przygotowanie i audyt danych]
    TEAM[Zespół: obserwacje i założenia] --> PREP
    PREP --> FILES[Wersjonowane dane i manifest]
    FILES --> MODEL[Model p-median i ABC]
    MODEL --> RESULTS[Wyniki CSV i JSON]
    RESULTS --> REPORT[Raport i wykresy offline]
    FILES -. planowane .-> UI[Przeglądarka: MapLibre i 3D]
    RESULTS -. planowane .-> UI
    UI -.-> TEACHER[Prowadzący i zespół]
    REPORT --> TEACHER
```

## Komponenty i przepływ danych

```mermaid
flowchart TD
    AOI[configs/agh-pilot.json: AOI i reguły] --> P[prepare_osm.py]
    RAW[Surowe odpowiedzi i graf: data/raw] --> P
    P --> MAP[map.geojson: graf i geometria]
    P --> PROBLEM[problem.json: punkty, wagi, macierz D]
    P --> MANIFEST[manifest.json: źródło, hashe, kontrola jakości]
    PROBLEM --> VALID[model.py: walidacja i funkcja celu]
    VALID --> ABC[solvers.py: ABC]
    VALID --> BASE[solvers.py: losowy i greedy + swap]
    VALID --> EXACT[solvers.py: małe optimum]
    ABC --> RUN[cli.py: wspólny runner]
    BASE --> RUN
    EXACT --> RUN
    RUN --> OUT[runs.csv, history.csv, results.json]
    OUT --> PLOT[report.py: mapa i zbieżność]
    MAP --> PLOT
    OUT -. docelowo .-> WEB[TypeScript + MapLibre]
    MAP -. docelowo .-> WEB
```

Zewnętrzne zapytania występują tylko w przygotowaniu danych. Domyślny benchmark i raport działają offline. Macierz `D[n_popyt, n_kandydaci]` oddziela koszt routingu od optymalizacji; identyfikatory i kolejność są częścią kontraktu. Jeden evaluator liczy wszystkie wywołania celu, w tym inicjalizację, powtórzenia, częściowe układy greedy i zwiadowczynie.

## Przebieg odtwarzalnego eksperymentu

```mermaid
sequenceDiagram
    participant U as Badacz
    participant CLI as CLI
    participant D as Snapshot plików
    participant M as Model
    participant S as Solver
    participant R as Raport
    U->>CLI: benchmark(p, budżet, scenariusz, ziarna)
    CLI->>D: Odczyt problem.json i hash
    CLI->>M: Walidacja odległości i normalizacja wag
    loop Metoda i niezależne ziarno
        CLI->>S: Ta sama instancja i limit ocen
        loop Do zatrzymania lub wyczerpania limitu
            S->>M: Oceń zbiór kandydatów
            M-->>S: Średnie dojście w metrach
        end
        S-->>CLI: Wynik, licznik, czas i historia
    end
    CLI->>D: CSV i JSON z parametrami
    U->>R: report
    R->>D: Weryfikacja hash i odczyt geometrii
    R-->>U: Mapa i wykres zbieżności
```

## Docelowy interfejs i ewentualne API

Pierwsza wersja interaktywna czyta `problem.json`, `map.geojson` i `results.json` z katalogu statycznego. Kontrolki wybierają już policzone `p`, scenariusz i metodę. Widok wyświetla kandydatów, popyt, wybrane stacje, rzeczywiste trasy po grafie, wynik w metrach, pokrycie i źródło danych. Zapisane wyniki ułatwiają powtórzenie demonstracji na laptopie.

Do rysowania tras trzeba zachować sekwencje krawędzi lub wygenerować `routes.geojson` dla wybranego rozwiązania. `map.geojson` pilota zachowuje `u`, `v` i długości, ale bieżący raport **jeszcze nie rysuje tras**. Nie wolno zastępować ich prostymi odcinkami opisanymi jako najkrótsze dojścia.

Jeśli po 20.11 potrzebna będzie optymalizacja z przeglądarki, proponowany kontrakt FastAPI to `POST /runs` (dataset ID, p, metoda, scenariusz, limit, seed), `GET /runs/{id}` (status, wynik) i `GET /datasets/{id}` (manifest). To projekt kontraktu, nie istniejące endpointy. Jeden proces obliczeniowy i pliki wystarczą na małą demonstrację. Każde żądanie musi mieć limit ocen i walidację parametrów. Nie uruchamiamy pobierania OSM w żądaniu użytkownika.

## Decyzje i uzasadnienie

| Decyzja | Uzasadnienie | Kiedy wrócić do decyzji |
|---|---|---|
| Dyskretny wybór kandydatów | łatwo zachować `p` różnych punktów i kontrolować teren | jeśli prowadzący wymaga współrzędnych ciągłych |
| Długość dojścia, nie dystans w linii prostej | uwzględnienie topologii sieci w modelu | jeśli audyt ujawni niekompletność ścieżek |
| Pliki + manifest | mały zespół, łatwe eksperymenty i odtwarzanie | jeśli wyniki przekroczą wygodny rozmiar repo |
| Lokalny Python, bez GPU | obliczenia macierzowe i mały obszar | po pomiarze wąskiego gardła |
| 3D w warstwie prezentacji | wysokości nie wpływają na funkcję celu | przy dodaniu wysokości/schodów do kosztu ruchu |
| Statyczny odczyt wyników przed API | niezależny rozwój mapy i badań | po ukończeniu podstawowego scenariusza interfejsu |

## Kontrole jakości

Warstwa danych odpowiada za dostępność i pochodzenie, model za jednostki i wagi, solver za wykonalność i budżet, runner za niezależne ziarna i porównywalność. CI nie kontaktuje się z OSM. Test snapshotu ponownie liczy odległości z wyeksportowanych krawędzi. Pozostaje obowiązek audytu terenowego: testy matematyczne nie potwierdzają fizycznej dostępności wejścia ani miejsca na stację.
