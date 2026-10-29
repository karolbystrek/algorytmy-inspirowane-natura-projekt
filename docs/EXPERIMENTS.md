# Protokół eksperymentów

## Warunki wspólne

Ta sama macierz odległości, wagi, zbiór kandydatów i `p` obowiązują wszystkie metody. Przed eksperymentem zamrażamy hash danych i konfigurację. Porównujemy **taki sam maksymalny budżet ocen celu**, a rzeczywistą liczbę ocen i czas podajemy osobno. Przeliczanie grafu i pobieranie OSM nie wchodzą do czasu solvera.

Losowanie sprawdza dopuszczalne zbiory bez powtórzeń wewnątrz układu. ABC obejmuje w budżecie inicjalizację, próby i zwiadowczynie. Powtórna ocena tego samego układu nadal kosztuje jedną ocenę. Greedy zaczyna od pustego zbioru, ocenia wszystkie możliwe dodania i po zbudowaniu układu wykonuje najlepsze zamiany 1-swap. Częściowe oceny też kosztują budżet. Dla `m` kandydatów budowa wymaga `p*m - p*(p-1)/2` ocen.

Greedy jest deterministyczne, więc uruchamiamy je **raz** na instancję, z jawnym rozróżnieniem „dodawanie + lokalne zamiany”. Kończy po braku poprawy lub limicie; nie dopychamy licznika fikcyjną pracą. W porównaniu z opisem wstępnym dodaliśmy lokalne zamiany, żeby uzyskać silniejszy punkt odniesienia. Czyste dodawanie można raportować jako osobny wariant. Gdy budżet nie wystarcza nawet do budowy, runner zwraca błąd.

Pełny przegląd jest **osobnym wzorcem poprawności**, bez wspólnego limitu heurystyk. Chronimy go limitem 200 000 kombinacji. Nigdy nie podpisujemy wyniku heurystyki „optimum”, jeśli nie ma dowodu. Losowanie i ABC wykonują 30 niezależnych przebiegów, ziarna `0..29` i generator PCG64. To samo ziarno służy odtwarzaniu, nie gwarantuje identycznego strumienia propozycji między algorytmami.

## Pilotaż na 9 listopada

Zestaw: 18 punktów popytu, 30 kandydatów, `p=4`, agregacja trzech scenariuszy, budżet 1000 ocen, ABC `foods=12`, `limit=30`, pokrycie w 250 m. `C(30,4)=27 405`, więc można policzyć dokładne optimum również dla całej małej instancji pilota.

```sh
uv sync --locked --all-extras
uv run agh-stations benchmark --p 4 --budget 1000 --runs 30 --exact --output outputs/demo
uv run agh-stations report --results outputs/demo
```

Podstawowy moduł ma też ręcznie policzalny test dwupunktowy. Liczymy niezależnie Dijkstrę z wyeksportowanych krawędzi i porównujemy ze snapshotem macierzy. Wyniki pilota nie potwierdzają rzeczywistych potoków ani wykonalności lokalizacji w terenie.

## Badanie końcowe

| Pytanie | Eksperyment | Priorytet |
|---|---|---|
| Czy ABC poprawia wynik względem punktów odniesienia? | `p ∈ {3,5,8}` lub wartości uzgodnione po audycie; agregacja; ABC i losowy po 30 ziaren, greedy raz | obowiązkowy |
| Ile daje kolejna stacja? | krzywa wynik/pokrycie dla tych samych `p`, ten sam zestaw punktów | obowiązkowy |
| Jak jeden układ służy porom dnia? | najlepszy układ agregowany oceniony w 3 scenariuszach; porównanie z oddzielnymi optymalizacjami każdego scenariusza | obowiązkowy |
| Czy wynik jest czuły na próg dostępności? | pokrycie tego samego układu dla `r ∈ {150,250,350}` m | obowiązkowy |
| Czy model zależy od arbitralnych wag? | wagi jednolite oraz wzrost/spadek wag kategorii o 25%, ponowna normalizacja | obowiązkowy |
| Jak wpływają parametry ABC? | `foods ∈ {8,12,24}`, `limit ∈ {15,30,60}` na instancji rozwojowej; stały budżet | po minimum |
| Czy istotny jest operator społeczny? | ABC z kierowaniem przez inne źródło vs losowa zamiana | po minimum |

Propozycja budżetu końcowego: 10 000 ocen na przebieg, po wcześniejszym pomiarze czasu. Nie jest to obietnica czasu odpowiedzi interfejsu. Ustalamy go raz dla porównania, przed oglądaniem rankingu. Instancja pilota służy do debugowania i strojenia; finał używa audytowanej wersji danych, a parametry wybieramy przed końcową serią. Jeśli pozostanie tylko jedna wersja danych, jawnie zgłaszamy brak niezależnego zbioru do oceny strojenia.

## Raportowanie

Dla metod losowych: najlepszy wynik, średnia, odchylenie standardowe próby (`ddof=1`), mediana i kwartyle, czas oraz faktyczny licznik ocen. Dla greedy: pojedynczy wynik i czas, bez sugerowania 30 niezależnych prób. Wykres zbieżności pokazuje medianę i kwartyle najlepszego kompletnego układu względem liczby ocen. Płaski dalszy odcinek greedy oznacza zachowany wynik po zakończeniu metody.

Luka do optimum: `100 × (F - F*) / F*`; dla `F*=0` raportujemy różnicę bezwzględną zamiast dzielenia przez zero. Jeśli optimum nie zostało policzone, podajemy „najlepszy znaleziony”, bez procentowej luki. Przed ewentualnym testem statystycznym trzeba ustalić pytanie i korektę wielokrotnych porównań; sam wynik pilota nie uzasadnia twierdzenia o ogólnej przewadze ABC.

Wersje, ziarna, hash i parametry są w `results.json`, wszystkie przebiegi w `runs.csv`, historia w `history.csv`. Zmiana danych lub parametrów oznacza nowy katalog wyników; nie mieszamy starych i nowych serii.
