# Co jeszcze warto dodać do projektu

Uzupełniający research: **29.10.2026**. Przeanalizowano obecną roadmapę, kod, wyniki pilota, dokumentację optymalizacji i źródła lokalne. Poniższe propozycje nie oznaczają, że funkcje zostały już zaimplementowane. Role pozostają robocze: Osoba A–F.

**Rekomendacja:** dołożyć ocenę najdłuższych dojść, sprawdzenie wpływu doboru punktów oraz zachować metadane potrzebne do 3D. Największy etap już jest w planie: audyt wejść, barier i kandydatów. Dla większego modelu przyda się solver MILP jako niezależny wzorzec. Dodatkowe metaheurystyki zostają za tymi zadaniami w kolejności prac.

## Nowe obserwacje na istniejącym pilocie

Obliczenia dotyczą tego samego snapshotu i najlepszego układu ABC z zapisanego eksperymentu. Użyto istniejącej funkcji celu i pełnego przeglądu. [diagnostics.json](../reports/pilot/diagnostics.json) zapisuje hashe oraz wyniki; reprodukcja: `uv run python scripts/inspect_pilot.py`.

| Metryka dla stałego układu, agregacja | Wynik |
|---|---:|
| Średnie ważone dojście | 343,645 m |
| Ważony percentyl 90 | 673,949 m |
| Najdłuższe dojście | 1225,532 m |
| Średnia w kategorii `dorm` | 237,193 m |
| Średnia w kategorii `teaching` | 269,628 m |
| Średnia w kategorii `other` | 614,350 m |

Percentyl oznacza najmniejszą odległość obejmującą co najmniej 90% **założonej masy popytu**. Nie jest pomiarem dojścia 90% studentów. Kategorie pochodzą z roboczej klasyfikacji budynków i wymagają audytu. Różnica między średnią a maksimum uzasadnia obejrzenie odległych punktów, ich wag i tras.

| Scenariusz | Stały układ [m] | Osobne optimum dla tego scenariusza [m] | Wzrost kosztu stałego układu |
|---|---:|---:|---:|
| Rano | 296,501 | 296,501 | 0,00% |
| Dzień | 351,754 | 324,880 | 8,27% |
| Wieczór | 382,681 | 349,096 | 9,62% |

To policzony przykład już zaplanowanej oceny kompromisu między porami dnia. Nie proponujemy przenoszenia stacji. Średnia po scenariuszach może być dobra przy gorszej obsłudze jednego z nich; warto pokazać tę tabelę na spotkaniu.

Dodatkowo dokładne optimum dla `p=3/4/5` wynosi odpowiednio **396,643 / 343,645 / 293,525 m**, a pokrycie w 250 m **39,58 / 45,83 / 50,00%**. Na tej instancji daje to prostą odpowiedź, co zyskujemy, dodając jedną stację. Wyniki nie wyznaczają liczby stacji do rzeczywistego wdrożenia.

## Priorytety i koszt

Szacunki oznaczają roboczogodziny zespołu; wymagają potwierdzenia przez wykonawców. Nie dodajemy całej tabeli do obowiązkowego zakresu.

| Propozycja | Co wnosi ponad obecny plan | Zalecenie | Szacunek |
|---|---|---|---:|
| Percentyl 90 i rozbicie wyników na kategorie | maksimum już jest liczone, ale nie ma P90 ani zestawienia kategorii w standardowym raporcie | dodać do raportu E03 | 1–2 h |
| Wpływ listy kandydatów i punktów popytu | obecna wrażliwość bada wagi i p, a pomija samo próbkowanie miejsc i budynków | dodać przed końcową serią, E04 | 3–5 h |
| Metadane wysokości dla 3D | obecny eksport budynków zawiera geometrię i ID, bez źródeł wysokości | doprecyzować istniejące D03/V03 | 1–2 h |
| Źródła AGH i mapa ZTP do audytu | konkretne źródła funkcji budynków i lokalnego kontekstu | włączyć w istniejące D03, bez osobnego dużego etapu | w ramach audytu |
| MILP / HiGHS jako wzorzec | ocena jakości większego modelu po przekroczeniu możliwości enumeracji | opcjonalne X04, jeśli obszar urośnie | 4–6 h |
| Trzy zewnętrzne instancje OR-Library | sprawdzenie solvera poza jedną geometrią AGH | opcjonalne X05 po minimum | 3–5 h |
| Zamknięcie jednego zweryfikowanego przejścia | odporność układu na zmianę sieci dojść | opcjonalnie po audycie, z jawnym opisem wariantu | 2–3 h |

Do 9 listopada wykorzystujemy gotowe tabele z diagnostyki i plan audytu. Do 4 grudnia rekomendowany dodatkowy koszt trzech pierwszych pozycji to **5–9 h**. Pokrywamy go z rezerwy 30 h, pozostawiając **21–25 h**. Jeśli wybierzemy MILP, rezerwa zmniejszy się do **15–21 h**; OR-Library i wariant zamknięcia przejścia wymagają kolejnej decyzji o czasie. Nie uruchamiamy wszystkich rozszerzeń równocześnie.

## 1. Wiarygodność wyniku zależy od punktów wejściowych

Obecny pilot wybiera 30 kandydatów metodą rozpraszania przestrzennego i 18 punktów popytu spośród większej liczby budynków. Optimum jest więc optimum **tej listy**, a nie wszystkich możliwych lokalizacji na kampusie. Sama zmiana parametrów ABC nie sprawdzi wpływu tej decyzji.

Proponowany eksperyment E04:

1. Ustalić jedną listę sprawdzonych budynków i kandydatów, z powodami pominięcia pozostałych. OSM pozostaje źródłem geometrii i sieci.
2. Porównać pełną listę kandydatów z dwoma ustalonymi podzbiorami przy tym samym p, popycie i grafie. Podzbiory mają być zagnieżdżone, np. połowa, trzy czwarte i całość. Dobór i kolejność ustalamy przed oglądaniem rankingu algorytmów.
3. W osobnym porównaniu zmieniać punkty popytu: obecna próbka vs pełniejsza lista wejść, przy stałych kandydatach. Opisać, jak zachowujemy sumę wag budynku, jeśli ma kilka wejść; nie powielać jego całego popytu w każdym wejściu.
4. Porównać wartości celu, pokrycie oraz zmianę lokalizacji stacji. Dla różnych list popytu stosować także wspólną, stałą listę do oceny, żeby zmiana średniej nie wynikała tylko z usunięcia odległych punktów.

Wniosek o wpływie modelowania oddzielamy od rankingu metod. [Przegląd dobrych praktyk benchmarkowania](https://arxiv.org/html/2007.03488v2) podkreśla precyzyjny opis instancji i granic uogólnienia wyników. Dobór podzbiorów i wspólnej listy oceny jest naszą propozycją dla AGH.

## 2. Solver MILP może być użyteczniejszym dodatkiem niż drugi rój

[PySAL/spopt](https://pysal.org/spopt/notebooks/p-median.html) opisuje p-median z przypisaniami punktów popytu do otwartych obiektów. Można użyć tej samej macierzy odległości oraz znormalizowanych wag co w ABC:

\[
\min \sum_{i,j}\bar q_i d_{ij}x_{ij},\quad
\sum_jx_{ij}=1,\quad \sum_jy_j=p,\quad x_{ij}\le y_j,\quad x_{ij},y_j\in\{0,1\}.
\]

`y_j` oznacza otwarcie stacji, `x_ij` przypisanie popytu. Proponujemy opcjonalny wrapper [scipy.optimize.milp / HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html), z osobnym limitem np. 60 s na instancję. Dokumentacja udostępnia status zakończenia, granicę dolną i lukę MIP. Zapisujemy je z tolerancją oraz oceną zwróconego układu przez wspólny evaluator. Limit czasu nie gwarantuje optimum; nawet status sukcesu trzeba interpretować w ustawionej tolerancji.

Najpierw porównujemy wynik z pełnym przeglądem pilota. Dla większej instancji solver może dostarczyć dowodu jakości lub tylko dolnego ograniczenia. Nie obiecujemy czasu rozwiązania modelu końcowego. Budżet MILP raportujemy oddzielnie od liczby ocen heurystyk. Biblioteki SciPy/spopt nie zostały przez ten research dodane do zależności projektu.

## 3. Benchmark zewnętrzny oddzieli jakość algorytmu od mapy

[OR-Library, p-median](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/pmedinfo.html) udostępnia 40 instancji i wartości optimum. To możliwe źródło trzech dodatkowych przypadków o różnych rozmiarach/p, po sprawdzeniu kosztu uruchomienia.

Ważny szczegół importu: pliki opisują krawędzie, a nie gotową macierz najkrótszych dróg. Instrukcja określa także obsługę wielokrotnych wpisów krawędzi: obowiązuje ostatni zapis, przed obliczeniem najkrótszych dróg. Przy wagach jednostkowych nasz evaluator liczy **średnią**, a wartości referencyjne są sumami kosztów; porównanie wymaga przemnożenia przez liczbę punktów. Jednostki tych kosztów nie muszą oznaczać metrów.

Adapter trzeba najpierw sprawdzić względem opublikowanego optimum. Wyniki zewnętrzne trafiają do osobnej tabeli; nie dowodzą poprawności danych kampusu. Warianty implementacji i ich budżety trzeba opisać, zgodnie z [Beiranvand, Hare, Lucet (2017)](https://doi.org/10.1007/s11081-017-9366-1). To rozszerzenie po minimum, a nie warunek pokazu 9 listopada.

## 4. Źródła lokalne i interpretacja dostępności

[Oficjalny wykaz akademików AGH](https://www.miasteczko.agh.edu.pl/strefa-mieszkanca/domy-studenckie.html) podaje nazwy, adresy i opisy budynków; dla DS Alfa także opis wejścia głównego. Może służyć jako odniesienie podczas sprawdzania klasyfikacji OSM i wyboru wejść. Nie utożsamiamy liczby miejsc ani opisu budynku ze zmierzonym popytem transportowym; informacja o wejściu nadal wymaga sprawdzenia połączenia z siecią.

[ZTP publikuje opis i mapę punktów mobilności](https://ztp.krakow.pl/miasto-15-minutowe/hulajnogi-elektryczne). Warto sprawdzić ich położenie względem zatwierdzonego obszaru badania i rozróżnić nową sieć od uzupełniania istniejącej. Research nie potwierdził liczby takich punktów wewnątrz naszego AOI ani gotowego eksportu danych do repo. Mapa jest źródłem do dalszej weryfikacji.

Jeśli porównujemy układ rzeczywisty z proponowanym, potrzebna jest ta sama liczba stacji albo oddzielne raportowanie wariantów o różnej liczbie. Stojak rowerowy w OSM nie jest automatycznie stacją pojazdów współdzielonych. Przy wariancie uzupełniania sieci istniejące stacje muszą stać się jawnie ustalonymi obiektami modelu.

Model p-median minimalizuje średnią, a [p-center](https://pysal.org/spopt/notebooks/p-center.html) minimalizuje najgorszy koszt dojścia. Dla naszego terminu pozostajemy przy p-median i dodajemy P90 oraz wyniki grupowe jako metryki. To nasza decyzja o zakresie; nowy cel wielokryterialny lub p-center wymagałby osobnego porównania.

## 5. Luka w danych do budynków 3D

Przegląd `prepare_osm.py` pokazał, że wybór kolumn pomija `height`, `min_height`, `building:levels` i `building:min_level`. Eksport GeoJSON budynków ma obecnie tylko geometrię, typ i ID. Z tych plików interfejs nie odczyta pochodzenia wysokości.

W ramach istniejącego V03 należy zachować te tagi przy przetwarzaniu oraz eksportować obliczoną wysokość w metrach i `height_source`. Reguła z wcześniejszego researchu pozostaje: rzeczywista wysokość, następnie liczba kondygnacji z jawnym przelicznikiem, potem oznaczona wartość zastępcza. Braki mają być widoczne w interfejsie. To doprecyzowanie kontraktu przed implementacją mapy 3D.

## Co pokazać prowadzącemu i co odłożyć

Na 9 listopada warto dodać do istniejącego scenariusza **jedną planszę z P90/maksimum i kompromisem dzień–wieczór** oraz krzywą `p=3/4/5`. Obliczenia są gotowe; omówienie zmieści się w obecnym bloku wyników. Pytanie o solver MILP i benchmark OR-Library dopisujemy do listy do uzgodnienia.

Przed końcem projektu najwięcej da audyt danych i sprawdzenie wpływu listy punktów. FA, API do obliczeń na żywo, pojemności, relokacja floty, ankieta masowa, prognoza ML i rozbudowa 3D poza wyciąganie obrysów pozostają rozszerzeniami. Nowy algorytm warto dodać dopiero, jeśli wymaga go prowadzący lub minimum jest ukończone.
