# Praca z repozytorium

Główna gałąź to `main`. Zmiany wprowadzamy przez krótkie gałęzie i pull requesty (odpowiednik MR na GitHubie). Dla zmian przygotowywanych przez Codex używamy prefiksu `codex/`; dla zespołu np. `feat/osm-audit`, `fix/distance-units`, `docs/experiment-protocol`.

## Mały cykl pracy

1. Wybierz zadanie z [backlogu](docs/BACKLOG.md), uzgodnij właściciela i kryterium odbioru.
2. Zaktualizuj gałąź względem `main`; nie łącz niepowiązanych zmian.
3. Uruchom `uv sync --locked --all-extras`, lint, format i testy z README.
4. W PR opisz problem, efekt i weryfikację; poproś jedną osobę o review. Zmianę danych zatwierdza również osoba od modelu.
5. Po poprawkach scal przez squash i usuń gałąź. Nie zmieniaj danych wejściowych w trakcie serii badań.

CI wykonuje walidację kodu, testy i mały eksperyment offline wraz z raportem. Pełna seria 30 ziaren jest osobną czynnością badawczą. Hashe w manifeście chronią przed przypadkowym mieszaniem wersji danych. Nie commitujemy `.venv`, cache OSM, sekretów ani nowych lokalnych wyników do `outputs/`.

## Etykiety i planowanie

Definicje etykiet są w [.github/labels.json](.github/labels.json). Obszary: dane, model, ABC, eksperymenty, wizualizacja i integracja. `priority:P0` oznacza minimum blokujące etap, `P1` normalne zadanie obowiązkowe, `P2` rozszerzenie. Odrębne etykiety opisują typ zmiany.

Skrypt nie nadpisuje istniejących etykiet i domyślnie tylko wyświetla brakujące. Wymaga zalogowanego GitHub CLI i dostępu do repo:

```sh
python3 scripts/sync_labels.py
python3 scripts/sync_labels.py --apply
```

Proponowane kamienie milowe Issues: `M1 — 2026-11-09`, `M2 — 2026-11-13`, `M3 — 2026-11-20`, `M4 — 2026-11-27`, `M5 — 2026-12-04`. Backlog w Markdown pozostaje punktem startowym; zadania nie są automatycznie przypisywane członkom zespołu.

## Tagi Git i wydania

Proponowana konwencja: `v0.1.0-pilot` po przyjęciu pierwszego modelu, `v0.2.0` po audycie danych, `v0.3.0` po interfejsie, `v1.0.0` dla projektu końcowego. **Tagujemy zaakceptowany commit na `main`**, po zielonym CI i krótkim opisie danych oraz ograniczeń. Sam PR nie jest wydaniem i nie oznacza ukończenia audytu. W pakiecie wydania umieszczamy konfigurację, snapshot, metryki i raport; większe surowe pliki przechowujemy jako artefakty.

Właściciel repo może dodatkowo ustawić wymóg review i obowiązkowego CI dla `main`. Ustawienia ochrony gałęzi oraz topics wymagają odpowiednich uprawnień i pozostają decyzją właściciela; instrukcja nie twierdzi, że zostały zmienione.
