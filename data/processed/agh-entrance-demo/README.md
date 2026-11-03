# Źródło demonstratora wejść 5 / 10 / 3

`source.json` jest samowystarczalnym, zamrożonym wycinkiem OSM: 472 węzły, 1080 skierowanych
krawędzi i 47 obrysów budynków. Nie wymaga lokalnego cache OSM ani połączenia z Overpass.
`configs/agh-entrance-demo.json` wybiera pięć wejść i dziesięć proponowanych miejsc.

Źródło grafu pochodzi ze stanu OSM **29.10.2026 17:47:06 UTC**, budynków ze stanu
**29.10.2026 17:52:10 UTC**. Oryginalne odpowiedzi były pobierane osobno; nie jest to jedna
transakcyjna migawka. SHA-256 oryginałów są w `lineage_sha256`, a hash tego wycinka w konfiguracji.
Wycinek utworzono przez wybór węzłów we wskazanym bbox, krawędzi między nimi i przecinających
obszar obrysów budynków. Zachowano OSM ID i tagi potrzebne do kontroli.

Model odrzuca jawne zakazy piesze, bramy wymagające potwierdzenia, warunkowe ograniczenia,
odcinki wewnętrzne i przejścia przez wnętrza pełnych budynków. Zadaszenia `building=roof`
nie są pełną przeszkodą na poziomie gruntu; zachowujemy istniejące w OSM ścieżki pod nimi.
Takie zadaszenia występują przy wejściach Olimpu i Strumyka. Źródło znaczenia tagu:
[OSM: building=roof](https://wiki.openstreetmap.org/wiki/Tag:building%3Droof).

Wejścia `entrance=main` należą do węzłów obrysu odpowiedniego akademika i grafu pieszych.
[Wykaz akademików AGH](https://www.miasteczko.agh.edu.pl/strefa-mieszkanca/domy-studenckie.html)
służy do sprawdzenia tożsamości budynków. Nie potwierdza aktualnej drożności wejść.

Dziesięć kandydatów wskazano w istniejących węzłach sieci, w pobliżu pięciu wejść, poza buforem
3 m od wszystkich obrysów i bez tagu bariery. Próbkę rozproszono przestrzennie, obejrzano na
wygenerowanej mapie i utrwalono ID. Węzły modelują lokalizacje proponowane, nie istniejące stacje
ani potwierdzoną dostępną powierzchnię. Minimalny odstęp kandydatów to 20 m.

**Dnia 03.11 użytkownik wybrał wyłącznie sprawdzenie mapowe; teren pozostaje `pending`.**
Do późniejszego audytu służy generowany `field-review-template.csv`. Skopiuj go poza katalog
wyników przed uzupełnianiem; ponowne uruchomienie odtwarza szablon.

Dane i pochodna baza: **© OpenStreetMap contributors**,
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/),
[informacja OSM](https://www.openstreetmap.org/copyright). Wagi i wybór obszaru są założeniami
projektu. Model uwzględnia tylko zapisany wycinek sieci.
