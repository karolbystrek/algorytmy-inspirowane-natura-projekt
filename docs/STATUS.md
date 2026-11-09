# Stan projektu — 09.11.2026

**Działa cały łańcuch na danych v2: od OSM, przez model i badania, po aplikację z trasami i budynkami 3D.** Projekt nie jest jeszcze gotowy do oddania, bo żaden punkt nie przeszedł audytu terenowego. Wyniki są wersją roboczą i opisują model, a nie gotową rekomendację miejsc.

## Co jest gotowe

| Obszar | Stan |
|---|---|
| Dane | `data/processed/agh-v2`: 101 punktów popytu, 99 kandydatów, wyciąg OSM z 8.11.2026. Pilot pozostaje niezmieniony i powtarzalny |
| Model i metody | p-median, ABC, losowanie, greedy z zamianami, dokładne optimum (MILP) dla każdego `p` |
| Strojenie ABC | osobna instancja rozwojowa; wybrano 8 źródeł i `limit = foods·p` |
| Badania | `agh-stations study`, wyniki w [reports/v2-draft](../reports/v2-draft), szkic w [REPORT_DRAFT.md](REPORT_DRAFT.md) |
| Aplikacja | FastAPI + React + MapLibre: mapa popytu, trasy dojścia, widok 3D, odtwarzanie popraw, działa offline |
| Audyt | [arkusz](../data/audit/agh-v2-audit.csv) i komenda `apply-audit`; **0 punktów sprawdzonych** |
| Kontrola | 110 testów, lint, build frontendu, próbne badania w CI |

## Najważniejsze wyniki robocze

- ABC jest istotnie lepsze od losowania i trafia w optimum w 26–30 z 30 przebiegów dla `p ∈ {3, 5, 8}`.
- Greedy z zamianami osiąga optimum dla `p = 3` i `8`, a dla `p = 5` traci 0,01%, zużywając mniej ocen. **Nie wykazaliśmy istotnej przewagi ABC nad greedy.**
- Główną dźwignią jakości ABC był limit porzucenia i pobieranie stacji z innych źródeł. Faza obserwatorek ma niewielki wpływ.
- Zmiana wag kategorii o ±25% prawie nie zmienia układu. Największy wpływ ma to, które budynki modelujemy i jak dzielimy między nie popyt.
- Stan 597 bram jest nieznany. Gdyby wszystkie były zamknięte, 10–15% popytu straciłoby drogę do stacji.

## Co musi zrobić zespół

1. **Audyt terenowy.** Zacząć od [listy priorytetów](../reports/v2-draft/candidates_to_check.csv), wpisywać decyzje do arkusza, potem `uv run agh-stations apply-audit`.
2. **Zatwierdzić granicę obszaru.** Akademiki na zachodzie MS leżą przy granicy prostokąta.
3. **Sprawdzić wagi**, zwłaszcza liczbę miejsc w akademikach, bo rozdział popytu między budynki najmocniej wpływa na wynik.
4. **Ustalić z prowadzącym** zakres ABC, potrzebę drugiego algorytmu oraz termin i format oddania.
5. Po audycie przeliczyć badania, uzupełnić raport i wkład członków zespołu, przećwiczyć pokaz na docelowym laptopie.

## Jak daleko jesteśmy względem planu

| Etap | Stan | Co pozostaje |
|---|---|---|
| M1 — pierwszy model | gotowe technicznie | próba na laptopie prezentacyjnym |
| M2 — wiarygodne dane | dane v2 gotowe, audyt otwarty | sprawdzenie punktów w terenie |
| M3 — kompletna aplikacja | gotowe na danych roboczych | uwagi zespołu, integracja danych po audycie |
| M4 — zamknięte badania | wersja robocza | przeliczenie na danych po audycie |
| M5 — oddanie | szkic raportu i slajdów | uzupełnienie, licencja kodu, próba na drugim komputerze |

Opis potwierdza działanie kodu i artefaktów. Nie potwierdza przeglądów terenowych ani uzgodnień zespołu.
