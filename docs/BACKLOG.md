# Backlog do Issues

Zadania odwołują się do roboczych ról **Osoba A–F** z [roadmapy](ROADMAP.md). Nie są przypisane do konkretnych członków zespołu; obsadę ustalimy później. `P0` oznacza blokadę etapu, `P1` pozostałe minimum, `P2` rozszerzenie.

| ID | Zadanie / proponowany właściciel | Termin / priorytet | Zależności | Kryterium odbioru |
|---|---|---|---|---|
| I01 | Uruchomienie pilota przez wszystkich / Osoba A | 30.10, P0 | ten PR | każdy odtwarza komendy README; co najmniej drugi laptop daje ten sam wynik celu |
| D01 | Zatwierdzić granicę obszaru / Osoba B + Osoba C | 02.11, P0 | — | wersjonowany poligon i opis, co jest włączone i dlaczego; obejrzane składowe odłączone |
| M01 | Zatwierdzić kontrakt danych / Osoba C | 02.11, P0 | D01 | jednostki, kolejność punktów, wagi, p i reguła niedostępności opisane; akceptacja przez solver i mapę |
| D02 | Sprawdzić pilota na mapie / Osoba B | 03.11, P0 | D01 | 5 tras zweryfikowanych wizualnie; jawna lista bram i wątpliwości; statystyki snapshotu |
| A01 | Przejrzeć dyskretny ABC / Osoba D | 04.11, P0 | M01 | opis operatora, kontrola faz i budżetu; review Osoby E; wyniki z ustalonymi ziarnami |
| E01 | Odtworzyć baseline’y i optimum / Osoba E | 04.11, P0 | M01 | niezależna kontrola małego przypadku i 27 405 kombinacji pilota, brak przekroczeń budżetu |
| V01 | Przygotować widok wyników na spotkanie / Osoba F | 05.11, P0 | D02, E01 | mapa pokazuje różnicę między kandydatem, popytem i wyborem; atrybucja; jawne ograniczenia |
| I02 | Zamrozić demo i przećwiczyć / Osoba A + wszyscy | 06.11, P0 | A01, E01, V01 | raport 30 ziaren, pliki offline, 10-minutowa próba, pytania do prowadzącego |
| D03 | Zweryfikować wejścia i kandydatów / Osoba B + Osoba C | 13.11, P0 | uwagi 09.11 | każdy punkt docelowy reviewed/rejected z powodem; legalny i fizyczny dostęp sprawdzony; poprawki lokalne |
| M02 | Popyt i dane v2 / Osoba C | 13.11, P0 | D03 | kategorie budynków sprawdzone; jawne wagi; 3 scenariusze i normalizacja; macierz po audycie |
| V02 | Interaktywna mapa wyników / Osoba F | 18.11, P0 | M01, zapis wyników | TypeScript/MapLibre czyta pliki; wybór p, scenariusza i metody; punkty oraz metryki |
| V03 | Trasy i budynki 3D / Osoba F + Osoba B | 20.11, P1 | V02, D03 | rzeczywiste sekwencje krawędzi; `height_source`; przybliżenia widoczne; wynik modelu niezależny od 3D |
| E02 | Zamrozić protokół końcowy / Osoba E + Osoba D | 20.11, P0 | M02 | budżet, p, parametry, ziarna i czas; oddzielone strojenie i ocena; pilotaż kosztu serii |
| E03 | Pełna seria i wrażliwość / Osoba E + Osoba C | 27.11, P0 | E02 | 30 ziaren, 3 wartości p, agregacja i porównania scenariuszy, próg i wagi; surowe wyniki + wykresy |
| I03 | Raport i prezentacja końcowa / Osoba A + wszyscy | 04.12, P0 | E03, V03 | problem, metoda, wyniki, ograniczenia, wkład 6 osób; odtworzenie na drugim komputerze |
| X01 | Ablacja operatora / Osoba D | po E03, P2 | E03 | porównanie na tym samym budżecie, bez zmiany końcowego protokołu |
| X02 | FastAPI dla obliczeń na żywo / Osoba A | po V03, P2 | V03 | walidacja, limit ocen, ID danych i wyników; brak pobierania OSM w żądaniu |
| X03 | Dyskretny Firefly / zainteresowana osoba | po I03, P2 | I03 | ten sam kontrakt, reprezentacja i protokół; ukończone minimum |

Proponowane etykiety to `area:*`, `type:*` i `priority:*` z [.github/labels.json](../.github/labels.json). Właściciela i recenzenta uzgadniamy przy rozpoczęciu zadania. Zadanie przekraczające 1–2 krótkie sesje warto rozbić na konkretny produkt, np. „lista wejść”, „warstwa poprawek”, „test spójności”.

## Propozycje po dodatkowym researchu

Poniższe pozycje wymagają wyboru przez zespół. Wskazane role są robocze; rozszerzenia X04/X05 nie są warunkiem pierwszego pokazu. Szacunki i źródła opisuje [research uzupełniający](RESEARCH_EXTENSIONS.md).

| ID / powiązanie | Propozycja / rola | Kiedy | Kryterium odbioru |
|---|---|---|---|
| E03 — doprecyzowanie | P90 i wyniki kategorii / Osoba E + Osoba C | do 27.11 | ważony P90, średnie i pokrycie grup, koszt stałego układu wobec optimów scenariuszy; jawny opis założonych wag |
| E04 — nowe | Wpływ listy kandydatów i popytu / Osoba E + Osoba C | po D03/M02, do 27.11 | trzy ustalone zagnieżdżone listy kandydatów; oddzielna zmiana punktów popytu i wspólna lista oceny; bez powielania wag wielu wejść |
| D03/V03 — doprecyzowanie | Źródła lokalne i wysokości / Osoba B + Osoba F | do 20.11 | weryfikacja funkcji budynków z wykazem AGH; sprawdzenie kontekstu ZTP; zachowane tagi wysokości, wysokość w metrach i `height_source` |
| X04 — opcjonalne | Wzorzec MILP / Osoba E | po M02 | zgodność z enumeracją pilota; osobny limit czasu, status, dolna granica i luka; układ oceniony wspólną funkcją celu |
| X05 — opcjonalne | Trzy instancje OR-Library / Osoba E + Osoba D | po minimum E03 | zweryfikowany import krawędzi i przeliczenie sumy/średniej; znane optima, parametry i porównywalny budżet heurystyk |
