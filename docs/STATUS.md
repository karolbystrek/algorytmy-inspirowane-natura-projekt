# Stan projektu przed prezentacją — 08.11.2026

**Mamy działający pilot modelu optymalizacyjnego i lokalne demo FastAPI + React.**
Można uruchomić obliczenia z przeglądarki, zobaczyć wybrane stacje na mapie i porównać
ABC z losowaniem oraz greedy. Najbliższy pokaz: **09.11.2026**. Cel końcowy według
[roadmapy](ROADMAP.md): **04.12.2026**; grudniowy zakres nie jest jeszcze ukończony.

## Co faktycznie działa

| Obszar | Gotowy element | Granica obecnej wersji |
|---|---|---|
| Dane | Lokalny snapshot OSM: 18 317 węzłów, 39 860 skierowanych krawędzi, obrysy budynków, 30 kandydatów i 18 punktów popytu | Kandydaci nie przeszli audytu terenowego; punkty popytu zastępują wejścia |
| Model | Dyskretny p-median: wybór dokładnie `p` różnych miejsc, średnie ważone dojście po grafie pieszym | Wagi są założeniami scenariuszy, a nie pomiarem ruchu; brak pojemności stacji i modelu floty |
| ABC | Inicjalizacja źródeł, fazy pracujących, obserwatorek i zwiadowczyń, zamiana jednego miejsca, stałe ziarno i budżet ocen | Własna adaptacja dyskretna, wymagająca omówienia z prowadzącym |
| Porównania | Losowanie, greedy z lokalnymi zamianami oraz dokładny pełny przegląd małych przypadków | Pełny przegląd ma osobny budżet i limit 200 000 kombinacji |
| Eksperymenty | CLI, 30 ziaren w zapisanym pilocie, statystyki, historia i pliki CSV/JSON, mapa i wykresy | Badanie na audytowanych danych i analiza wrażliwości pozostają do wykonania |
| Aplikacja | FastAPI + React/TypeScript, mapa Leaflet offline, konfiguracja, porównanie metod, suwak odtwarzania i eksport JSON | Pojedynczy przebieg na metodę; mapa 2D, bez narysowanych tras i 3D |
| Kontrola poprawności | Testy modelu, budżetów, powtarzalności, API i zgodności macierzy z grafem; CI dla Pythona i buildu frontendu | Testy nie potwierdzają fizycznej dostępności lokalizacji ani bram |

## Jak działa jedno uruchomienie

1. Użytkownik ustawia liczbę stacji i scenariusz. W sekcji **Parametry zaawansowane**
   może zmienić budżet ocen, ziarno oraz włączyć lub wyłączyć dokładne optimum.
2. React wysyła `POST /api/run` do lokalnego FastAPI. API sprawdza parametry, a przy pierwszym odczycie weryfikuje hashe
   zamrożonych plików. Nie pobiera OSM ani kafelków mapy.
3. Te same solvery co w CLI dostają tę samą macierz dojść, wagi, `p` i maksymalny
   budżet ocen. Dla każdego punktu popytu wybierana jest najbliższa stacja z układu;
   funkcja celu sumuje te odległości z unormowanymi wagami.
4. ABC utrzymuje 12 źródeł. Próbuje zamian jednego miejsca, częściej wybiera obiecujące
   źródła, a po stagnacji zastępuje porzucone źródło losowym. Poprawy najlepszego
   pełnego układu są zapisywane wraz z numerem oceny i listą stacji.
5. API zwraca końcowe wyniki ABC, losowania i greedy oraz ich zapis popraw. Opcjonalnie
   sprawdza wszystkie kombinacje i zwraca udowodnione optimum tego małego przypadku.
6. Mapa i duże metryki pokazują **wybrany krok wybranej metody**. Tabela porównuje
   **wyniki końcowe**. Odtwarzanie jest animacją zapisu po zakończeniu obliczeń,
   nie transmisją całej populacji pszczół w czasie rzeczywistym.
7. Eksport JSON zapisuje parametry, hash danych, metryki, wybrane stacje i kroki.
   Po zainstalowaniu zależności i zbudowaniu interfejsu cały pokaz działa offline.

Domyślnie: `p=4`, agregacja trzech scenariuszy, seed `0`, budżet `1000` ocen na
heurystykę, próg pokrycia `250 m`. UI pozwala wybrać `p=1..12` i do 20 000 ocen.
Greedy może zatrzymać się przed limitem. Dokładne optimum jest dostępne w UI dla
`p ≤ 5`; nie porównujemy jego kosztu z budżetem heurystyk. API obsługuje jeden
eksperyment naraz. Instrukcja startu jest w [README](../README.md#demo-fastapi--react-na-prezentację).

## Co mówią wyniki pilota

Poniższe liczby dotyczą zapisanej serii **30 ziaren**, a nie pojedynczego uruchomienia
widocznego w przeglądarce. Instancja: 30 kandydatów, 18 punktów popytu, `p=4`,
agregacja, budżet 1000 ocen dla heurystyk. Źródło: [raport pilota](../reports/pilot/README.md)
oraz jego [surowe wyniki](../reports/pilot/runs.csv).

| Metoda | Przebiegi | Średnie dojście [m] | Najlepszy wynik [m] | Oceny na przebieg |
|---|---:|---:|---:|---:|
| ABC | 30 | 343,837 | 343,645 | 1000 |
| Losowanie | 30 | 366,791 | 346,523 | 1000 |
| Greedy + 1-swap | 1 | 343,645 | 343,645 | 426 |
| Pełny przegląd | 1 | 343,645 | 343,645 | 27 405, osobny budżet |

ABC osiąga optimum w **28 z 30** przebiegów. To kontrola, że pilot potrafi znaleźć
bardzo dobry układ, ale **nie dowód przewagi ABC nad greedy**: greedy również znajduje
optimum i potrzebuje tu mniej ocen. Wyniki jednej małej instancji z założonymi wagami
nie wystarczają do ogólnych wniosków o metodach ani do rekomendacji miejsc w terenie.

## Weryfikacja tej wersji

Na komputerze deweloperskim 08.11 przeszły: **36 testów**, lint i formatowanie Pythona,
build TypeScript/React oraz ponowne obliczenie serii 30 ziaren i raportu offline.
W przeglądarce sprawdzono zmianę konfiguracji, nowe obliczenia, odtwarzanie, wybór metody,
eksport JSON oraz układ laptopowy i mobilny. Poprawiono również przewijanie: karta
ustawień przewija się z treścią i nie przykrywa wykresów, także po rozwinięciu parametrów.
CI uruchamia kontrole Pythona, mały eksperyment offline i build frontendu; jego
aktualny wynik należy sprawdzić przy PR.
Próba na drugim laptopie lub projektorze nie została tu potwierdzona.

## Jak daleko jesteśmy względem planu

| Etap | Ocena na 08.11 | Co pozostaje |
|---|---|---|
| M0 — kontrakt | Schemat i snapshot są używane przez model, CLI, API i interfejs | Uzgodnienie docelowej granicy, ról i założeń przez zespół nie jest potwierdzone kodem |
| M1 — pierwszy model | Technicznie działa cały przepływ od danych do algorytmów, porównania i mapy; jest zapis 30 ziaren | Próba na laptopie prezentacyjnym, review zespołu i potwierdzenie zakresu z prowadzącym |
| M2 — wiarygodne dane | Otwarte | Audyt wejść, bram i kandydatów; udokumentowane poprawki; dane v2 |
| M3 — kompletna aplikacja | Częściowo: interaktywne demo 2D i obliczenia z przeglądarki są gotowe wcześniej | Rzeczywiste trasy dojścia, 3D i integracja audytowanych danych |
| M4 — zamknięte badania | Jest protokół i pilot | Końcowe dane i parametry, seria eksperymentów, scenariusze, wrażliwość i interpretacja |
| M5 — oddanie | Jest instrukcja i scenariusz pierwszego pokazu | Końcowy raport, prezentacja i odtworzenie całego pakietu |

Nie przeliczamy tego na procent ukończenia: uruchomienie aplikacji nie zastępuje
audytu danych ani końcowych badań. Realny stan to **pierwszy działający model wraz
z demonstratorem**, z rozpoczętą wcześniej częścią interfejsową etapu M3.

## Najbliższe kroki

1. **Przed 09.11:** uruchomić demo na laptopie docelowym, przećwiczyć zmianę `p`
   i scenariusza, przygotować zapisane PNG jako plan awaryjny.
2. **09.11:** omówić z prowadzącym dyskretne ABC, założony popyt, zakres porównań
   i wymagania oddania. Pytania są w [scenariuszu spotkania](MEETING_2026-11-09.md).
3. **Do 13.11:** priorytetem jest audyt danych, nie nowy algorytm. Sprawdzić wejścia,
   ograniczenia dostępu i fizyczną możliwość umieszczenia stacji.
4. **Następnie:** dodać trasy po grafie, domknąć wizualizację i przeprowadzić
   [protokół końcowych eksperymentów](EXPERIMENTS.md) na zamrożonych danych po audycie.

Role i terminy w [backlogu](BACKLOG.md) pozostają propozycją do potwierdzenia przez
zespół. Ten opis potwierdza działanie kodu i dostępność artefaktów, nie wykonanie
przeglądów terenowych ani organizacyjnych.
