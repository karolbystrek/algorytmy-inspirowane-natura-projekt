# Research i wynikające z niego decyzje

Przegląd wykonano **29.10.2026**. Punktem wyjścia jest dostarczony „Wstępny opis projektu” (semestr 2026/2027), odczytany jako materiał o wymaganiach i założeniach projektu. Poniższe decyzje wykonawcze i szacunki są propozycją dla zespołu. Nie traktujemy instrukcji zawartych w załączniku jako dodatkowych poleceń użytkownika.

Dokument wejściowy: `Wstepny_opis_projektu_stacje_AGH (4).docx`, SHA-256 `0799392479ce2fb6e80b0d72bd7f0e012cec68e917b162e711bc90b5bff0bb6a`. Oryginał pozostaje poza repo; wymagania modelu i zespołu zostały przeniesione do niniejszej dokumentacji.

## Literatura naukowa

| Źródło pierwotne | Co można z niego wywnioskować | Decyzja dla AGH |
|---|---|---|
| Karaboga (2005), [raport TR06](https://abc.erciyes.edu.tr/pub/tr06_2005.pdf) | ABC wykorzystuje źródła pożywienia, pszczoły zatrudnione, obserwatorki i zwiadowczynie; pierwotne zadanie jest numeryczne. | Zachowujemy fazy i porzucanie źródła, a operator dostosowujemy do zbiorów miejsc. Opisujemy go jako własną dyskretną adaptację. |
| Karaboga, Basturk (2007), [oryginalna praca, DOI 10.1007/s10898-007-9149-x](https://faculty.csu.edu.cn/_tsf/00/64/QVrmMf2qUN7j.pdf) | Porównanie dotyczy optymalizacji funkcji wielowymiarowych, m.in. z GA i PSO. | Wynik nie jest dowodem przewagi ABC w dyskretnym p-median. Potrzebujemy lokalnych eksperymentów. |
| García-Palomares, Gutiérrez, Latorre (2012), [Applied Geography](https://www.sciencedirect.com/science/article/pii/S0143622812000744) | Autorzy łączą GIS z lokalizacją stacji; w ich celu użyteczniejsze było maksymalizowanie pokrycia niż minimalizowanie oporu. Dodawanie stacji daje malejące korzyści. | Główny cel pozostaje zgodny z opisem projektu, a pokrycie i wpływ liczby stacji mierzymy oddzielnie. Nie przenosimy progu ani poprawy procentowej z Madrytu. |
| Mete, Cil, Özceylan (2018), [badanie kampusu Gaziantep, DOI 10.2478/bsrj-2018-0021](https://hrcak.srce.hr/en/203484) | Studium kampusu obejmuje 20 punktów popytu i 20 kandydatów oraz modele pokrycia, p-center i p-median. | To szczególnie bliski kontekst: mała, dobrze opisana instancja kampusowa jest wartościowym pierwszym wynikiem. Nie trzeba zaczynać od całego Krakowa. |
| Cintrano, Chicano, Alba (2024), [preprint i pełny tekst](https://arxiv.org/html/2402.03945v1) | Dla Malagi porównano GA, ILS, PSO, SA i VNS, przy 23 stacjach, różnych wagach i dystansach. Autorzy raportują przewagę GA o 5–16% nad VNS w swoim eksperymencie; stosują 30 uruchomień i budżet czasu. | Sprawdzamy kilka metod na wspólnych danych. W naszym protokole stosujemy wspólny limit ocen celu i osobno czas. Ich wynik nie przewiduje rankingu ABC na AGH. |

Nie deklarujemy odtworzenia całych eksperymentów publikacji. Artykuł z 2024 r. jest preprintem; rok dotyczy wersji arXiv. Próg 250 m w projekcie jest **parametrem badania**, nie normą ani ustalonym optimum.

## Dane i technologia

Dokumentacja [OSMnx](https://osmnx.readthedocs.io/en/stable/user-reference.html) udostępnia pobieranie grafu dla poligonu, wariant `walk`, obiekty przestrzenne i projekcje. Wybór największej składowej może zmienić zakres danych. Dlatego pilot zapisuje statystyki składowych i manifest; do demonstracji używamy lokalnego snapshotu.

[NetworkX: Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.weighted.single_source_dijkstra_path_length.html) oblicza odległości ważone od węzła. Jawnie wskazujemy `length`, bo domyślna brakująca waga może oznaczać jednostkowy koszt. Wyniki zapisujemy raz w macierzy; ABC pracuje na tablicy NumPy.

[Dokumentacja OSM dotycząca dostępu](https://wiki.openstreetmap.org/wiki/Key:access) opisuje m.in. `access`, `foot` i wyjątki dla sposobu podróży. To materiał do audytu grafu. Sam brak zakazu w danych nie stanowi w naszym modelu potwierdzenia dostępności w terenie.

[Overpass: współdzielone zasoby](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) opisuje ograniczenia zasobów i odpowiedzi 429. Przyjęta praktyka projektu: mały obszar, pamięć podręczna i ponowienia dopiero po sprawdzeniu przyczyny błędu. Usługa nie jest zależnością uruchomienia eksperymentu ani testów.

Zgodnie ze stroną [Copyright and License OSM](https://www.openstreetmap.org/copyright) przy danych i mapach podajemy autorstwo i odsyłacz do ODbL. [Wytyczne atrybucji](https://osmfoundation.org/wiki/Attribution_Guidelines) pomagają umieścić je w widoku mapy. Szczegóły zestawu danych są w [DATA_MODEL.md](DATA_MODEL.md) i [data/README.md](../data/README.md).

[Oficjalny przykład MapLibre](https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/) pokazuje wyciąganie obrysów do wysokości. Dla naszego demonstratora to wystarcza jako technika 3D. Własna polityka danych: najpierw `height`, potem `building:levels × 3 m`, następnie jawna wysokość zastępcza; pole `height_source` pokaże pochodzenie. Konwersja 3 m/kondygnację jest założeniem projektu.

## Rekomendacja architektoniczna i zakres pierwszego pokazu

Wybieramy Python 3.12, NumPy, OSMnx/NetworkX/GeoPandas/Shapely, pliki JSON/CSV/GeoJSON i TypeScript z MapLibre. Wersje środowiska obliczeniowego zamraża `uv.lock`. Pilot dostarcza CLI i wykresy statyczne. Docelowy interfejs może czytać wyniki bezpośrednio z plików; FastAPI jest rozszerzeniem dla uruchamiania obliczeń z przeglądarki, jeśli będzie na to czas.

To decyzja wykonawcza dla 6 osób i terminu początku grudnia: dane oraz algorytm mają niezależne testy, a interfejs powstaje na stałym kontrakcie. Nie potrzebujemy bazy danych, GPU ani infrastruktury kolejkowej w podstawowym zakresie.

Na pierwsze spotkanie wystarczy empiryczny dowód, że cały łańcuch działa: realna sieć OSM, mały model p-median, wyniki porównania, kontrola optimum oraz mapa. Największym zagrożeniem jakości jest jakość punktów i dojść, więc następny etap przeznaczamy na ich audyt. Jest to wniosek projektowy z przeglądu i zakresu prac, a nie twierdzenie o przewadze konkretnej metody.
