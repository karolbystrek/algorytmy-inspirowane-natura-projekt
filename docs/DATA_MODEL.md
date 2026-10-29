# Model i kontrakt danych

## Problem optymalizacji

Niech `I` będzie zbiorem punktów popytu, `J` kandydatów, `p` liczbą stacji, a `d_ij` długością najkrótszego dopuszczalnego dojścia w metrach. Dla scenariusza `s` definiujemy nieujemne wagi `w_i^s` o dodatniej sumie. Normalizujemy **każdy scenariusz osobno**:

\[
q_i^s = w_i^s / \sum_{k \in I} w_k^s, \qquad
F_s(S)=\sum_{i \in I}q_i^s\min_{j \in S}d_{ij}.
\]

Dla jednego stałego układu stacji używamy mieszaniny scenariuszy:

\[
\bar q_i=\sum_s\alpha_s q_i^s,\quad \sum_s\alpha_s=1,
\qquad \min_{S\subseteq J,\ |S|=p}F(S)=\sum_i\bar q_i\min_{j\in S}d_{ij}.
\]

Raportujemy także ważone pokrycie `C_r(S) = Σ_i q_i · 1[min_j d_ij ≤ r]`, maksymalne dojście i wyniki każdego scenariusza. Oddzielna optymalizacja rano/w dzień/wieczorem jest odniesieniem dla oceny stałego układu, a nie zaleceniem przenoszenia stacji w ciągu dnia. Pilot ma równe `α_s = 1/3`.

## Reprezentacja i operator ABC

Źródło pożywienia to posortowana krotka `p` różnych indeksów kandydatów. Ruch usuwa jeden punkt i dodaje jeden spoza zbioru. W połowie prób, jeśli istnieje różnica między źródłami, dodawany punkt pochodzi z innego źródła; w pozostałych przypadkach losujemy z całego dopełnienia. Zachowujemy zawsze `p` i brak duplikatów.

Zatrudnione pszczoły wykonują po jednej próbie dla każdego źródła. Obserwatorki wybierają źródła proporcjonalnie do `1 / (1 + F)`. Po `limit` nieudanych próbach zwiadowczyni zastępuje najbardziej wyczerpane źródło losowym; najwyżej jedno zastąpienie na cykl. Globalny najlepszy wynik jest przechowywany niezależnie. Jest to **dyskretna adaptacja projektu**, nie implementacja ciągłego wzoru ABC z zaokrąglaniem współrzędnych.

`foods=12` oznacza liczbę źródeł / pszczół zatrudnionych i tyle samo prób obserwatorek na pełny cykl. Raportowanie „wielkości kolonii” musi wskazywać tę konwencję. Pilot kończy się limitem ocen celu, nie liczbą cykli.

## Pliki wersji 1

| Plik | Kontrakt |
|---|---|
| `configs/agh-pilot.json` | `bbox_wgs84` w kolejności zachód, południe, wschód, północ; bufor routingu; liczba punktów; reguły; metryczny CRS |
| `problem.json` | `schema_version=1`, ID zestawu, uporządkowane `candidates` i `demand`, `distances_m`, `scenarios`, `scenario_mixture` |
| `map.geojson` | WGS84; budynki, skierowane krawędzie `u/v/length_m`, kandydaci i punkty popytu; bez pobierania kafelków |
| `manifest.json` | konfiguracja, czas zebrania, endpoint, wersje bibliotek, SHA-256, liczebności i ograniczenia |
| `runs.csv` | metoda, seed, p, scenariusz, faktyczna liczba ocen, czas, metryki i ID wyboru |
| `history.csv` | zdarzenia poprawy najlepszego kompletnego układu, z numerem oceny; między zdarzeniami wynik jest stały; częściowe układy greedy nie są dopuszczalnymi wynikami |
| `results.json` | parametry wywołania, hash problemu, statystyki i najlepsze rozwiązania każdej metody |

Wiersz `i` macierzy odnosi się do `demand[i]`, kolumna `j` do `candidates[j]`. Każdy punkt ma trwałe ID; indeks ma znaczenie tylko wewnątrz tego snapshotu. Wszystkie odległości wersji 1 są skończone i nieujemne. Błędne rozmiary, wagi, duplikaty ID i nieskończone odległości powodują błąd, a nie zastąpienie braków zerem. Metryczne bufory i dobór przestrzenny liczymy w EPSG:2180. GeoJSON przechowuje długość i szerokość geograficzną.

## Co dokładnie oznaczają dane pilota

Granica jest roboczym prostokątem obejmującym MS AGH i część kampusu, **nie oficjalną granicą AGH**. Graf pobieramy z dodatkowym buforem, żeby nie odcinać objazdów przy krawędzi. Używamy niesimplifikowanego grafu pieszych, usuwamy jawne zakazy `foot=no/private` i `access=no/private` bez dopuszczającego wyjątku pieszego. Zachowujemy największą silnie spójną składową; jej udział i inne składowe są w manifeście. Przed wersją docelową trzeba ocenić, czy wykluczenia nie usuwają istotnego popytu.

Automatycznie wybieramy 30 kandydatów w węzłach grafu, poza buforem 3 m od obrysów budynków. **Wszyscy mają `status=requires_review`**: nie sprawdzono własności, miejsca na stację, przeszkód, wody ani zgody administratora. Odstęp 3 m to filtr pilota, nie norma lokalizacyjna.

18 punktów popytu to węzły grafu najbliższe punktom reprezentatywnym wybranych budynków. Zachowujemy ID budynku i odległość `proxy_offset_m`. **Nie są to sprawdzone wejścia**; koszt przejścia od budynku do węzła nie wchodzi do funkcji celu pilota. Odległości między samymi węzłami są rzeczywistymi najkrótszymi drogami na pobranym grafie, ale pełne dojście „od drzwi” wymaga następnego etapu.

Wagi względnej aktywności w pilotażu:

| Kategoria z tagów OSM | Rano | Dzień | Wieczór |
|---|---:|---:|---:|
| `dorm`: `building=dormitory` | 4 | 1 | 4 |
| `teaching`: university/college/school lub amenity=university | 3 | 5 | 1 |
| `other`: pozostałe wybrane budynki | 1 | 2 | 3 |

To ilustracyjne założenia o aktywności, bez jednostki „liczba studentów”. Funkcja budynku z OSM może być niepełna; sprawdzamy ją ręcznie przed raportem końcowym. Większy obrys służy jedynie do priorytetu próbkowania, nie jest pomiarem liczby mieszkańców. Pilot nie obsługuje godzin otwarcia i warunkowych ograniczeń; liczbę odpowiednich tagów i bram podaje manifest.

## Audyt wymagany przed badaniem końcowym

1. Zatwierdzić granicę i zachować wersję; obejrzeć odłączone składowe, bramy, przejścia przez ulice, schody i brakujące ścieżki.
2. Dla każdego budynku wskazać dostępne wejście i zweryfikowane połączenie z siecią. Połączenia do krawędzi wymagają jej podziału i poprawnego kosztu. Sprawdzić, czy łącznik nie przecina budynku, ogrodzenia ani innej przeszkody.
3. Dla każdego kandydata zapisać `reviewed/rejected`, przyczynę, datę oraz źródło obserwacji. W docelowym solverze dopuścić wyłącznie `reviewed`.
4. Poprawki przechowywać lokalnie jako osobną warstwę z pochodzeniem; edycja publicznego OSM to osobna czynność zespołu po weryfikacji.
5. Przeliczyć macierz i hashe. Niespójny punkt musi wywołać błąd lub uzasadnioną zmianę zakresu; nigdy nie znika bez wpisu w audycie.

## Pochodzenie i licencja danych

Geometria i sieć: **© OpenStreetMap contributors**, dane [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), [informacja OSM](https://www.openstreetmap.org/copyright). Pochodną bazę pilota udostępniamy na ODbL; dane założeń oznaczamy osobno. Atrybucja jest także na wygenerowanej mapie. Licencja danych nie ustala licencji kodu źródłowego całego projektu.
