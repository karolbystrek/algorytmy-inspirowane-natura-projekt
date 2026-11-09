# Rozmieszczenie stacji rowerów i hulajnóg na MS AGH — szkic raportu

> **Wersja robocza z 09.11.2026.** Żaden z 99 kandydatów nie został jeszcze sprawdzony w terenie, więc wyniki opisują model, a nie gotową rekomendację lokalizacji. Po audycie trzeba przeliczyć badania jedną komendą (rozdział 8) i zaktualizować liczby. Miejsca do uzupełnienia przez zespół oznaczono **[DO UZUPEŁNIENIA]**.

## 1. Streszczenie

Wybieramy `p` lokalizacji stacji rowerów lub punktów postoju hulajnóg na Miasteczku Studenckim AGH i w przyległej części kampusu, minimalizując średnie ważone dojście po rzeczywistej sieci pieszej OpenStreetMap. Główną metodą jest dyskretna adaptacja algorytmu sztucznej kolonii pszczół (ABC), porównana z wyszukiwaniem losowym, metodą zachłanną z lokalnymi zamianami oraz dokładnym optimum wyznaczonym programowaniem całkowitoliczbowym.

Na instancji kampusowej (101 punktów popytu, 99 kandydatów, budżet 10 000 ocen) ABC było istotnie lepsze od losowania i trafiało w optimum w 28–30 z 30 przebiegów. **Nie wykazano przewagi ABC nad metodą zachłanną**: ta znalazła optimum przy każdym badanym `p`, używając mniej ocen. Solver dokładny rozwiązuje tę instancję w ułamku sekundy, więc wartość projektu leży w zbadaniu zachowania metody rojowej, a nie w konieczności jej użycia.

## 2. Problem

Zadanie ma postać dyskretnego problemu p-median. Dla punktów popytu `I`, kandydatów `J` i odległości `d_ij` szukamy zbioru `S ⊆ J`, `|S| = p`, minimalizującego `Σ_i q_i · min_{j∈S} d_ij`, gdzie `q_i` to znormalizowana waga popytu. Docelowy układ jest stały w ciągu dnia, dlatego wagi to równa mieszanina trzech osobno znormalizowanych scenariuszy (rano, w dzień, wieczorem). Pełne definicje są w [DATA_MODEL.md](DATA_MODEL.md). Dodatkowo raportujemy pokrycie, czyli udział ważonego popytu w zasięgu 250 m.

Model zakłada dostępność pojazdu i miejsca zwrotu. Nie obejmuje pojemności stacji, bilansowania floty ani prognozy popytu.

## 3. Dane

Źródłem jest wyciąg OpenStreetMap dla Małopolski z Geofabrik, stan z 8.11.2026 (21:21 UTC). Sieć piesza ma 18 329 węzłów i 39 894 skierowane krawędzie, a obszar zawiera 1340 obrysów budynków.

| Element | Wartość |
|---|---|
| Punkty popytu | 101: 22 akademiki, 71 budynków uczelnianych, 8 innych celów (biblioteka, hale sportowe, przychodnia, klub, handel) |
| Dojście od budynku | 54 budynki mają wejścia z OSM; pozostałe używają punktu obrysu najbliższego grafowi |
| Łączniki | proste odcinki do grafu, najdłuższy 22 m; w 17 budynkach nie potwierdzono łącznika omijającego przeszkody |
| Kandydaci | 99: 47 parkingów rowerowych z OSM, 2 parkingi hulajnóg, 50 węzłów sieci do 150 m od popytu, co najmniej 70 m od siebie |
| Audyt terenowy | **0 z 99 kandydatów sprawdzonych** |

W stosunku do pierwszego pilota (18 punktów popytu, 30 kandydatów) lista miejsc przestała ograniczać wynik. Gdyby postawić stacje we wszystkich kandydatach, średnie dojście wyniosłoby 46,7 m przy pełnym pokryciu 250 m, wobec 183,4 m i 81% w pilocie.

Wagi są założeniami, nie pomiarami ruchu. Suma wag każdej kategorii pochodzi z tabeli scenariuszy, a w obrębie kategorii dzielimy ją według powierzchni użytkowej budynku (obrys × kondygnacje). Dla 32 budynków liczbę kondygnacji przyjęto jako medianę kategorii.

## 4. Algorytm ABC

Źródło pożywienia to zbiór `p` różnych kandydatów. Ruch usuwa jeden element i dodaje inny, z prawdopodobieństwem 0,5 pochodzący z innego źródła. Pszczoły pracujące próbują poprawić każde źródło, obserwatorki wybierają źródła proporcjonalnie do `1/(1+F)`, a zwiadowczyni zastępuje źródło porzucone po `limit` nieudanych próbach. Najlepszy układ jest przechowywany niezależnie od populacji.

Parametry dobrano na **osobnej instancji rozwojowej** (losowe punkty na tym samym grafie, 60 punktów popytu, 150 kandydatów, `p ∈ {5, 10, 20}`, 10 przebiegów), więc strojenie nie widziało danych końcowego porównania. Siatka objęła `foods ∈ {8, 12, 24}` i `limit ∈ {15, 30, 60, foods·p}`. Wybrano `foods = 8`, `limit = foods·p`.

Najważniejszym parametrem okazał się limit porzucenia. Dla 8 źródeł strata do optimum przy `limit = 30` wynosiła 2,17% (`p = 10`) i 3,97% (`p = 20`), a przy `limit = foods·p` odpowiednio 0,02% i 0,34%. Regułę `limit = SN·D` spotyka się w literaturze o ABC **[DO UZUPEŁNIENIA: źródło]**.

Wpływ mechanizmów ABC na instancji rozwojowej (średnia strata do optimum, 10 przebiegów):

| Wariant | p = 5 | p = 10 | p = 20 |
|---|---:|---:|---:|
| Wybrane ABC | 0,00% | 0,02% | 0,34% |
| Bez inspiracji innym źródłem | 1,47% | 3,15% | 3,84% |
| Obserwatorki rangowe | 0,26% | 0,06% | 0,53% |
| Bez fazy obserwatorek | 0,09% | 0,20% | 0,33% |
| Greedy + zamiany (jeden przebieg) | 0,00% | 0,00% | 0,11% |

Kluczowe jest pobieranie stacji z innych źródeł. Faza obserwatorek ma niewielki wpływ: funkcja `1/(1+F)` przy wartościach rzędu setek metrów prawie nie różnicuje źródeł, a zamiana na selekcję rangową nie poprawiła wyniku.

## 5. Protokół eksperymentów

Wszystkie metody korzystają z tej samej macierzy odległości i limitu 10 000 ocen funkcji celu. ABC i losowanie wykonują po 30 przebiegów (ziarna 0–29), a deterministyczne greedy jeden. Optimum każdej instancji dowodzi solver HiGHS, zweryfikowany testami z pełnym przeglądem. Pytanie statystyczne ustalono przed obliczeniami: czy ABC daje mniejsze dojście niż losowanie (jednostronny test Manna-Whitneya, korekta Holma). Szczegóły są w [EXPERIMENTS.md](EXPERIMENTS.md).

## 6. Wyniki

| p | Optimum [m] | ABC: średnia [m] | ABC: trafienia | Losowanie: średnia [m] | Losowanie: strata | Greedy [m] | Greedy: oceny |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 300,87 | 300,87 | 30/30 | 309,87 | 2,99% | 300,87 | 870 |
| 5 | 226,00 | 226,00 | 29/30 | 244,37 | 8,13% | 226,00 | 1425 |
| 8 | 156,69 | 156,81 | 28/30 | 195,83 | 24,98% | 156,69 | 3676 |

ABC jest istotnie lepsze od losowania dla każdego `p` (skorygowane p ≈ 2,6·10⁻¹²). Greedy osiąga optimum za każdym razem i potrzebuje mniej ocen, a przewaga ABC nad nim nie występuje. Także na trudniejszej instancji rozwojowej greedy było co najmniej tak dobre jak ABC.

![Zbieżność metod](../reports/v2-draft/convergence.png)

Korzyść z kolejnych stacji wyraźnie maleje. Przejście z 1 na 2 stacje skraca średnie dojście o 294 m, z 4 na 5 o 27 m, a z 10 na 11 o 10 m. Celem optymalizacji jest odległość, a nie pokrycie, dlatego pokrycie nie musi rosnąć z każdą stacją: dla `p = 10` wynosi 85,0%, a dla `p = 11` i `12` spada do 84,5%.

| p | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 15 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Średnie dojście [m] | 658 | 364 | 301 | 253 | 226 | 199 | 157 | 135 | 116 | 96 |
| Pokrycie 250 m | 3,6% | 35,7% | 49,4% | 54,2% | 59,4% | 63,4% | 77,5% | 85,0% | 84,5% | 94,1% |

![Korzyść z kolejnych stacji](../reports/v2-draft/stations_curve.png)

![Układ optymalny dla 5 stacji](../reports/v2-draft/layout_map.png)

### Wrażliwość

**Pora dnia.** Stały układ zoptymalizowany dla całego dnia traci względem układu dobranego osobno dla danej pory:

| p | Rano | W dzień | Wieczorem |
|---:|---:|---:|---:|
| 3 | 6,70% | 1,06% | 0,00% |
| 5 | 6,57% | 11,72% | 0,00% |
| 8 | 0,00% | 10,28% | 7,42% |

**Próg dostępności** (pokrycie tego samego układu):

| p | 150 m | 250 m | 350 m |
|---:|---:|---:|---:|
| 3 | 25,7% | 49,4% | 65,1% |
| 5 | 35,7% | 59,4% | 76,4% |
| 8 | 50,5% | 77,5% | 91,6% |

**Założone wagi.** Zmiana wagi jednej kategorii o ±25% prawie nie zmienia wyniku: strata układu bazowego wynosi co najwyżej 2,6%, a dla `p = 3` układ pozostaje identyczny. Silnie działa natomiast sposób rozdziału popytu między budynki. Równy podział w kategorii daje stratę 4,6–6,6% i zachowuje 2 z 3, 2 z 5 oraz 4 z 8 stacji. Wagi jednakowe dla wszystkich budynków dają stratę 9,6–18,4%. **Rozmiar budynków jest więc założeniem o największym wpływie na wynik i powinien zostać zweryfikowany**, np. danymi o liczbie miejsc w akademikach.

## 7. Ograniczenia

- Żadna lokalizacja nie została sprawdzona w terenie, a dane OSM mogą nie odzwierciedlać ogrodzeń, bram i własności terenu.
- Wagi nie pochodzą z pomiarów ruchu.
- Obszar jest roboczym prostokątem. Akademiki w zachodniej części MS leżą blisko jego granicy, więc granicę trzeba zatwierdzić.
- Łączniki od wejść do grafu są odcinkami prostymi, a w 17 budynkach przebieg łącznika pozostaje niepotwierdzony.
- Parametry ABC dobrano na instancji rozwojowej z tym samym grafem, ale innymi punktami i wagami. Wnioski o ABC dotyczą tego problemu i tej skali.
- Porównanie obejmuje jedną metodę rojową. Algorytm świetlików pozostaje opcjonalnym rozszerzeniem, którego nie wykonano.

## 8. Odtworzenie

```sh
uv sync --locked --all-extras
uv run agh-stations study --output outputs/study
```

Dane są zamrożone w repozytorium, a ich hashe zapisuje manifest. Procedura audytu terenowego jest opisana w [DATA_MODEL.md](DATA_MODEL.md#audyt-terenowy). Priorytety sprawdzania wyznacza [candidates_to_check.csv](../reports/v2-draft/candidates_to_check.csv): pierwsze 10 pozycji z 31 pojawia się w układach optymalnych najczęściej.

## 9. Wkład członków zespołu

**[DO UZUPEŁNIENIA przez zespół.]**

## 10. Literatura

1. Karaboga, D., Basturk, B. (2007). A powerful and efficient algorithm for numerical function optimization: artificial bee colony (ABC) algorithm. *Journal of Global Optimization*, 39, 459–471.
2. García-Palomares, J. C., Gutiérrez, J., Latorre, M. (2012). Optimizing the location of stations in bike-sharing programs: A GIS approach. *Applied Geography*, 35(1–2), 235–246.
3. Cintrano, C., Chicano, F., Alba, E. (2024). Using metaheuristics for the location of bicycle stations. Preprint, arXiv:2402.03945.
4. Dane: © OpenStreetMap contributors, licencja ODbL 1.0.
