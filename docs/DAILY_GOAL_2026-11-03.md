# Cel na 3 listopada: demonstrator 5 / 10 / 3

Cel: pięć konkretnych wejść do akademików, dziesięć proponowanych miejsc stacji, wybór trzech stacji i pięć tras po grafie. Porównujemy istniejące ABC, greedy z zamianami i pełny przegląd; całość ma powstawać jedną komendą.

## Uzgodniony zakres weryfikacji

**3 listopada użytkownik zdecydował: dziś tylko źródła mapowe, potwierdzenie terenowe później.** Dane i raport muszą pokazywać ten status. Sprawdzenie OSM i geometrii nie potwierdza fizycznej dostępności, wolnego miejsca ani zgody na ustawienie stacji. Obsada ról pozostaje Osoba A–F.

Wybrany obszar: okolice DS Olimp, Babilon, Filutek, Strumyk i Kapitol. Używamy jawnie oznaczonych wejść z OSM połączonych ze ścieżkami; nie zastępujemy wejść środkami budynków. Wagi popytu w małym demonstratorze są jednakowe i założone.

## Kryteria ukończenia

- [x] Pięć wejść ma OSM ID, wskazany budynek i połączenie z grafem.
- [x] Dziesięć kandydatów ma OSM ID węzła, uzasadnienie i status weryfikacji mapowej.
- [x] Trasy omijają wnętrza pełnych budynków i odrzucone przejścia; punkty są osiągalne.
- [x] ABC, greedy i pełny przegląd wybierają po trzy różne miejsca.
- [x] Pięć tras na mapie ma długości zgodne z macierzą i wynikiem modelu.
- [x] Jedna komenda odtwarza porównanie i raport offline z zamrożonych danych.
- [x] Testy i niezależne uruchomienie w CI potwierdzają działanie.
- [x] Zmiany są w PR do `main`, z opisem ograniczeń.

## Iteracje

1. Źródła i konkretne wejścia: wybrano pięć wejść `entrance=main`, należących do obrysów akademików i grafu pieszych OSM. Kontrola terenowa pozostaje odroczona.
2. Kandydaci, graf i porównanie: 10 propozycji poza buforem 3 m obrysów i bez tagu bariery;
   po filtrach graf ma 436 węzłów i 984 krawędzie. Wszystkie 50 par wejście–kandydat są osiągalne.
3. Mapa tras i kontrola źródeł: pięć tras zapisano jako krawędzie OSM. Kontrola wykryła
   zadaszenia przy Olimpie i Strumyku; `building=roof` zachowuje istniejące ścieżki pod dachem,
   a pełne wnętrza budynków są blokowane. Odrzucono 12 skierowanych krawędzi wnętrz,
   84 krawędzie ze względu na typ/dostęp lub usunięte węzły i 10 węzłów dostępu/barier.
4. Kontrole lokalne: 34 testy, lint, formatowanie, wheel i sdist. Test całości blokuje HTTP
   i połączenia sieciowe. CI ma dodatkowe uruchomienie demonstratora na czystym checkout.

## Gotowy rezultat lokalny

```sh
uv run --all-extras agh-stations demo
```

Polecenie zapisuje `outputs/entrance-demo/report.html`, mapę PNG/SVG, sekwencje krawędzi
`routes.geojson`, wyniki wszystkich metod, manifest i szablon do późniejszej kontroli terenowej.
Gotowa kopia raportu jest w [reports/entrance-demo](../reports/entrance-demo/README.md).

Najlepszy układ: **S01, S02, S07**, średnie dojście **50,291 m**. ABC i losowanie w 30 przebiegach
odnajdują tę samą wartość co greedy z zamianami oraz pełny przegląd 120 kombinacji. Jest to
mała instancja kontrolna; nie wykazuje przewagi jednej metody i nie jest porównywalna z wynikiem
343,645 m pilota 18/30, który ma inny obszar i popyt.

| Wejście | Stacja | Długość [m] |
|---|---|---:|
| DS Olimp | S01 | 14,69 |
| DS Babilon | S01 | 85,74 |
| DS Filutek | S07 | 17,36 |
| DS Strumyk | S07 | 66,28 |
| DS Kapitol | S02 | 67,38 |

Każdy punkt i każda trasa zachowują status **teren: do potwierdzenia**, zgodnie z ustalonym
zakresem na dziś. Tabela dotyczy grafu OSM z 29 października, wyciętego do opisanego obszaru.

## Zamknięcie celu w uzgodnionym zakresie mapowym

Implementacja i raport są w [PR #3 do main](https://github.com/karolbystrek/algorytmy-inspirowane-natura-projekt/pull/3).
[CI dla implementacji](https://github.com/karolbystrek/algorytmy-inspirowane-natura-projekt/actions/runs/41610387587)
zakończyło się sukcesem: 34 testy, lint, formatowanie, odtworzenie obu demonstratorów offline
i zapis artefaktów. To niezależne uruchomienie na runnerze GitHub Actions; sprawdzenie na laptopie
członka zespołu i fizyczna kontrola miejsc pozostają późniejszymi czynnościami.

**Dzisiejszy cel mapowy zrealizowany.** Odroczenie terenu pozostaje jawne w danych, raporcie,
szablonie kontroli i opisie PR. Nie jest traktowane jako wykonana weryfikacja terenowa.
