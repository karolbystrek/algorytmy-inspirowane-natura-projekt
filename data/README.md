# Dane

`processed/agh-pilot/` zawiera mały snapshot do demonstracji i testów offline:

- `problem.json`: macierz dojść, punkty i założone wagi;
- `map.geojson`: geometria i krawędzie grafu;
- `manifest.json`: pochodzenie, konfiguracja, hashe i raport jakości.

**Geometria i sieć © OpenStreetMap contributors.** Dane OSM i pochodną bazę pilota udostępniamy na [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Zobacz [informację o prawach OSM](https://www.openstreetmap.org/copyright). Wagi popytu i robocza granica obszaru są założeniami projektu. Kandydaci i lokalizacje popytu wymagają audytu; szczegóły w [kontrakcie danych](../docs/DATA_MODEL.md).

`raw/` jest lokalną pamięcią podręczną, ignorowaną przez Git. Do ponownego pobrania:

```sh
uv run --extra geo agh-stations prepare-osm
```

Konfiguracja wskazuje obszar i reguły; jej hash identyfikuje pliki podręczne. Bez `--refresh` wykorzystujemy istniejące surowe pliki. `--refresh` prosi o ponowne przetworzenie źródła, lecz OSMnx nadal może użyć własnej pamięci odpowiedzi. Aby świadomie pobrać nowy stan, wskaż **nowy** `--raw-dir` i `--output`; dotychczasowy snapshot pozostaw do odtworzenia badań. Nie uruchamiaj odświeżania podczas pokazu ani w CI.

Gotowy snapshot wystarcza do identycznych wartości celu i wyboru stacji w tym samym środowisku. Żywe OSM zmienia się, więc ponowne pobranie po czasie nie jest odtworzeniem identycznych danych. Pełne surowe pliki można przechować z wydaniem końcowym; w repo pozostaje wyeksportowana sieć umożliwiająca ponowne sprawdzenie macierzy.
