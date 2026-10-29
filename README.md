# Rozmieszczenie stacji na MS AGH

Projekt na przedmiot **Algorytmy inteligentne inspirowane naturą**, zespół 6 osób, semestr 2026/2027. Wybieramy `p` stacji rowerowych / punktów postoju hulajnóg, minimalizując średnie ważone dojście po grafie pieszym OpenStreetMap. Główna metoda: dyskretny **Artificial Bee Colony (ABC)**.

**Pierwszy pokaz: 9 listopada 2026. Gotowy projekt: 4 grudnia; rezerwa do około 15 grudnia.**

## Od czego zacząć

| Dokument | Zawartość |
|---|---|
| [Roadmapa](docs/ROADMAP.md) | etapy, proponowane role 6 osób, zależności i kryteria ukończenia |
| [Spotkanie 09.11](docs/MEETING_2026-11-09.md) | co pokazać, scenariusz prezentacji, pytania i plan awaryjny |
| [Research](docs/RESEARCH.md) | źródła naukowe i techniczne oraz decyzje dla projektu |
| [Dodatkowy research](docs/RESEARCH_EXTENSIONS.md) | co jeszcze warto dodać, priorytety, źródła lokalne i nowe obserwacje z pilota |
| [Architektura](docs/ARCHITECTURE.md) | diagramy kontekstu, komponentów i przebiegu eksperymentu |
| [Model i dane](docs/DATA_MODEL.md) | funkcja celu, reprezentacja ABC, kontrakty i ograniczenia |
| [Eksperymenty](docs/EXPERIMENTS.md) | uczciwe porównanie metod, budżety, ziarna i metryki |
| [Backlog](docs/BACKLOG.md) | zadania gotowe do przeniesienia do Issues |
| [Praca z repo](CONTRIBUTING.md) | PR, CI, etykiety i wersjonowanie |

## Działający pilot

Repo zawiera snapshot grafu OSM, 18 zastępczych punktów popytu i 30 kandydatów, model p-median, ABC, losowanie, greedy z lokalnymi zamianami, pełny przegląd oraz generator mapy i wykresów. Dane i założenia są opisane w [data/README.md](data/README.md).

**To demonstrator modelu:** wagi popytu są założone, punkty reprezentują węzły grafu zamiast sprawdzonych wejść, a kandydaci wymagają weryfikacji w terenie. Interaktywna mapa, trasy i budynki 3D są zaplanowane w roadmapie.

Wymagania: [uv](https://docs.astral.sh/uv/getting-started/installation/) i Python 3.12 (uv może pobrać interpreter). Po instalacji zależności poniższe obliczenia działają offline:

```sh
uv sync --locked --all-extras
uv run agh-stations benchmark --p 4 --budget 1000 --runs 30 --exact
uv run agh-stations report
```

W `outputs/demo/` powstaną `runs.csv`, `history.csv`, `results.json`, `map.png/svg` i `convergence.png/svg`. Gotowy zapis pilota znajduje się w [reports/pilot](reports/pilot/README.md).

Ponowne pobranie OSM wymaga internetu; jest oddzielone od eksperymentów:

```sh
uv run --extra geo agh-stations prepare-osm
```

Kontrole przed PR:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Struktura

```text
configs/                  granica obszaru i założenia przygotowania danych
data/raw/                 lokalny cache, poza Git
data/processed/agh-pilot/  zamrożone dane do obliczeń offline
src/agh_stations/          model, solvery, przygotowanie OSM, CLI i wykresy
tests/                    poprawność celu, budżetu i routingu ze snapshotu
docs/                     roadmapa, research, architektura i backlog
reports/pilot/            zapis wyników i ilustracje pierwszego modelu
outputs/                  nowe wyniki lokalne, poza Git
.github/                  CI, szablony Issues/PR i definicje etykiet
```

Geometria i sieć: **© OpenStreetMap contributors**, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), [informacja OSM](https://www.openstreetmap.org/copyright). Licencja danych jest opisana oddzielnie od kodu; zespół powinien ustalić licencję kodu przed wydaniem końcowym.
