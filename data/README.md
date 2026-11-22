# Dane

`processed/agh-pilot/` to pierwszy, mały zestaw danych, zachowany do testów i CI:

- `problem.json`: macierz dojść, punkty i założone wagi;
- `map.geojson`: geometria i krawędzie grafu;
- `manifest.json`: pochodzenie, konfiguracja, hashe i raport jakości.

**Geometria i sieć © OpenStreetMap contributors.** Dane OSM i pochodną bazę pilota udostępniamy na [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Zobacz [informację o prawach OSM](https://www.openstreetmap.org/copyright). Wagi popytu i robocza granica obszaru są założeniami projektu. Szczegóły są w [raporcie](../docs/REPORT.md).

`processed/agh-v2/` to dane do badania końcowego: wszystkie istotne budynki, ich wejścia i kandydaci blisko popytu. Opis danych jest w [raporcie](../docs/REPORT.md#3-dane). `processed/agh-development/` służy wyłącznie do strojenia parametrów; to losowe punkty, których nie wolno przedstawiać jako wyniku dla kampusu.

`raw/` jest lokalną pamięcią podręczną, ignorowaną przez Git. Dane `agh-v2` odtwarza się z wyciągu OSM według konfiguracji `configs/agh.json`:

```sh
uv run --extra geo agh-stations prepare-v2 --pbf ścieżka/malopolskie-latest.osm.pbf
```

Bez `--pbf` generator korzysta z Overpass. Aby pobrać nowy stan OSM, wskaż **nowy** `--raw-dir` i `--output`; dotychczasowe dane pozostaw do odtworzenia badań.

Gotowy snapshot wystarcza do identycznych wartości celu i wyboru stacji w tym samym środowisku. Żywe OSM zmienia się, więc ponowne pobranie po czasie nie jest odtworzeniem identycznych danych. Pełne surowe pliki można przechować z wydaniem końcowym; w repo pozostaje wyeksportowana sieć umożliwiająca ponowne sprawdzenie macierzy.
