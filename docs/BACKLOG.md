# Backlog do Issues

Zadania mają proponowanych właścicieli zgodnie z [roadmapą](ROADMAP.md). To lista planistyczna; nie utworzono automatycznych przypisań ani powiadomień do członków zespołu. `P0` oznacza blokadę etapu, `P1` pozostałe minimum, `P2` rozszerzenie.

| ID | Zadanie / proponowany właściciel | Termin / priorytet | Zależności | Kryterium odbioru |
|---|---|---|---|---|
| I01 | Uruchomienie pilota przez wszystkich / Jan | 30.10, P0 | ten PR | każdy odtwarza komendy README; co najmniej drugi laptop daje ten sam wynik celu |
| D01 | Zatwierdzić granicę obszaru / Karol + Patryk | 02.11, P0 | — | wersjonowany poligon i opis, co jest włączone i dlaczego; obejrzane składowe odłączone |
| M01 | Zatwierdzić kontrakt danych / Patryk | 02.11, P0 | D01 | jednostki, kolejność punktów, wagi, p i reguła niedostępności opisane; akceptacja przez solver i mapę |
| D02 | Sprawdzić pilota na mapie / Karol | 03.11, P0 | D01 | 5 tras zweryfikowanych wizualnie; jawna lista bram i wątpliwości; statystyki snapshotu |
| A01 | Przejrzeć dyskretny ABC / Patrick | 04.11, P0 | M01 | opis operatora, kontrola faz i budżetu; review Mateusza; wyniki z ustalonymi ziarnami |
| E01 | Odtworzyć baseline’y i optimum / Mateusz | 04.11, P0 | M01 | niezależna kontrola małego przypadku i 27 405 kombinacji pilota, brak przekroczeń budżetu |
| V01 | Przygotować widok wyników na spotkanie / Gabriel | 05.11, P0 | D02, E01 | mapa pokazuje różnicę między kandydatem, popytem i wyborem; atrybucja; jawne ograniczenia |
| I02 | Zamrozić demo i przećwiczyć / Jan + wszyscy | 06.11, P0 | A01, E01, V01 | raport 30 ziaren, pliki offline, 10-minutowa próba, pytania do prowadzącego |
| D03 | Zweryfikować wejścia i kandydatów / Karol + Patryk | 13.11, P0 | uwagi 09.11 | każdy punkt docelowy reviewed/rejected z powodem; legalny i fizyczny dostęp sprawdzony; poprawki lokalne |
| M02 | Popyt i dane v2 / Patryk | 13.11, P0 | D03 | kategorie budynków sprawdzone; jawne wagi; 3 scenariusze i normalizacja; macierz po audycie |
| V02 | Interaktywna mapa wyników / Gabriel | 18.11, P0 | M01, zapis wyników | TypeScript/MapLibre czyta pliki; wybór p, scenariusza i metody; punkty oraz metryki |
| V03 | Trasy i budynki 3D / Gabriel + Karol | 20.11, P1 | V02, D03 | rzeczywiste sekwencje krawędzi; `height_source`; przybliżenia widoczne; wynik modelu niezależny od 3D |
| E02 | Zamrozić protokół końcowy / Mateusz + Patrick | 20.11, P0 | M02 | budżet, p, parametry, ziarna i czas; oddzielone strojenie i ocena; pilotaż kosztu serii |
| E03 | Pełna seria i wrażliwość / Mateusz + Patryk | 27.11, P0 | E02 | 30 ziaren, 3 wartości p, agregacja i porównania scenariuszy, próg i wagi; surowe wyniki + wykresy |
| I03 | Raport i prezentacja końcowa / Jan + wszyscy | 04.12, P0 | E03, V03 | problem, metoda, wyniki, ograniczenia, wkład 6 osób; odtworzenie na drugim komputerze |
| X01 | Ablacja operatora / Patrick | po E03, P2 | E03 | porównanie na tym samym budżecie, bez zmiany końcowego protokołu |
| X02 | FastAPI dla obliczeń na żywo / Jan | po V03, P2 | V03 | walidacja, limit ocen, ID danych i wyników; brak pobierania OSM w żądaniu |
| X03 | Dyskretny Firefly / zainteresowana osoba | po I03, P2 | I03 | ten sam kontrakt, reprezentacja i protokół; ukończone minimum |

Proponowane etykiety to `area:*`, `type:*` i `priority:*` z [.github/labels.json](../.github/labels.json). Właściciela i recenzenta uzgadniamy przy rozpoczęciu zadania. Zadanie przekraczające 1–2 krótkie sesje warto rozbić na konkretny produkt, np. „lista wejść”, „warstwa poprawek”, „test spójności”.
