# Stan projektu — 09.11.2026

**Działa cały łańcuch na danych v2: od OSM, przez model i badania, po aplikację z trasami i budynkami 3D.** Pełny raport i prezentacja zakładają, że audyt terenowy potwierdzi obecne dane. Audytu jeszcze nie wykonano, więc rekomendacja miejsc jest warunkowa, a po audycie badania trzeba przeliczyć.

## Co jest gotowe

| Obszar | Stan |
|---|---|
| Dane | `data/processed/agh-v2`: 101 punktów popytu, 99 kandydatów, wyciąg OSM z 8.11.2026. Pilot pozostaje niezmieniony i powtarzalny |
| Model i metody | p-median, ABC, algorytm genetyczny, losowanie, greedy z zamianami, dokładne optimum (MILP) dla każdego `p` |
| Strojenie | osobna instancja rozwojowa; ABC: 8 źródeł i `limit = foods·p`; GA: populacja 100, mutacja 0,4, krzyżowanie losowe |
| Badania | `agh-stations study`, wyniki w [reports/v2-draft](../reports/v2-draft), raport w [REPORT.md](REPORT.md) |
| Aplikacja | FastAPI + React + MapLibre: mapa popytu, trasy dojścia, widok 3D, odtwarzanie popraw, krzywa liczby stacji, analiza grup budynków i pór dnia, seria ziaren, działa offline |
| Audyt | [arkusz](../data/audit/agh-v2-audit.csv) i komenda `apply-audit`; **0 punktów sprawdzonych** |
| Kontrola | 139 testów, niezależna kontrola tras, lint, build frontendu, próbne badania w CI |

## Najważniejsze wyniki robocze

- Waga budynku wynika teraz z jego powierzchni i założonego natężenia ruchu. Kategoria „inne” ma 6,4% popytu zamiast sztucznych 25%.
- ABC jest istotnie lepsze od losowania i trafia w optimum w 18–30 z 30 przebiegów dla `p ∈ {3, 5, 8}`.
- GA i ABC są równorzędne: dla `p ∈ {3, 5, 8}` różnice nie są istotne, a przy większym `p` prowadzenie zależy od liczby stacji i budżetu.
- **Nie wykazaliśmy ogólnej przewagi ABC nad prostymi metodami.** Do `p = 8` lokalne przeszukiwanie jest równie dobre. Z greedy ABC wygrywa, gdy greedy utyka w optimum lokalnym (`p = 3, 8, 10`) lub kończy mu się budżet (`p = 20, 25`). Duże straty lokalnego przeszukiwania przy `p ≥ 15` wynikają głównie z jego kosztownego wariantu.
- Rekomendacja przy pozytywnym audycie: 6 stacji (184 m, 75% popytu w 250 m), potem rozbudowa do 15 (109 m, 95%).
- Główną dźwignią jakości ABC był limit porzucenia i pobieranie stacji z innych źródeł. Faza obserwatorek ma niewielki wpływ.
- Zmiana natężenia kategorii o ±25% prawie nie zmienia układu. Największy wpływ ma to, które budynki modelujemy i jaką mają powierzchnię.
- Układ odporny obniża najgorszą stratę między porami dnia kosztem 0,5–3,2% średniej z całego dnia.
- Stan 597 bram jest nieznany. Gdyby wszystkie były zamknięte, 10,8% popytu straciłoby drogę do stacji.

## Co musi zrobić zespół

1. **Audyt terenowy.** Zacząć od [listy priorytetów](../reports/v2-draft/candidates_to_check.csv), wpisywać decyzje do arkusza, potem `uv run agh-stations apply-audit`.
2. **Zatwierdzić granicę obszaru.** Akademiki na zachodzie MS leżą przy granicy prostokąta.
3. **Sprawdzić wagi**, zwłaszcza natężenia w `configs/agh-v2.json` i liczbę miejsc w akademikach, bo rozdział popytu między budynki najmocniej wpływa na wynik.
4. **Ustalić z prowadzącym** termin i format oddania.
5. Po audycie przeliczyć badania i zaktualizować liczby w raporcie, uzupełnić wkład członków zespołu, przećwiczyć pokaz na docelowym laptopie.

## Jak daleko jesteśmy względem planu

| Etap | Stan | Co pozostaje |
|---|---|---|
| M1 — pierwszy model | gotowe technicznie | próba na laptopie prezentacyjnym |
| M2 — wiarygodne dane | dane v2 gotowe, audyt otwarty | sprawdzenie punktów w terenie |
| M3 — kompletna aplikacja | gotowe na danych roboczych | uwagi zespołu, integracja danych po audycie |
| M4 — zamknięte badania | komplet przy założeniu pozytywnego audytu | przeliczenie na danych po audycie |
| M5 — oddanie | pełny raport i slajdy | wkład zespołu, licencja kodu, próba na drugim komputerze |

Opis potwierdza działanie kodu i artefaktów. Nie potwierdza przeglądów terenowych ani uzgodnień zespołu.
