<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Globale Datenquellen für Streaming-Verfügbarkeiten von TV-Serien

Die nachfolgende Analyse stellt sieben aktuelle Datenanbieter vor, mit denen Sie weltweit für jede TV-Seriemitteln können, auf welchem Streamingdienst und in welcher Region (z.B. Netflix Deutschland) sie verfügbar ist. Alle Dienste unterstützen IMDb- oder TMDb-IDs und bieten Free- oder Low-Cost-Tarife.

## Überblick

Wer eine persönliche App, ein internes Dashboard oder ein Hobby-Projekt bauen möchte, braucht:

- weltweite Kataloge, die pro Land den konkreten Streamingdienst nennen,
- Lookup per eindeutiger Serien-ID (IMDb oder TMDb),
- ein Preismodell, das im privaten Rahmen erschwinglich ist (Free-Tier oder ≤\$30/Monat).

Die folgende Bewertung vergleicht Reichweite, Features, Preis, API-Qualität und rechtliche Rahmenbedingungen der Kandidaten.

## Bewertete Anbieter

### 1. TMDB Watch Providers

Die Movie Database (TMDb) stellt unter `/tv/{tv_id}/watch/providers` ländergetrennte Provider-Listen bereit.  [^1][^2]

- Abdeckung: >180 Länder, Datenquelle JustWatch.  [^3]
- IDs: TMDb-ID direkt, IMDb-ID via `/find`.
- Preis: vollständig gratis, Rate-Limits 40 req/10 s.  [^4]
- Einschränkung: Liefert nur „wo zu sehen“, keine Deeplinks oder Preise; Monetarisierungstyp-Filter kombinieren sich teils nicht korrekt.  [^5]


### 2. Streaming Availability API (Movie-of-the-Night)

Kompletter OTT-Katalog von 20+ Diensten in 60 Ländern, abrufbar über RapidAPI.  [^6][^7]

- IDs: IMDb oder TMDb in einem einzigen Endpunkt.  [^8]
- Gratis-Kontingent: 100 Requests/Tag.  [^9]
- Bezahl­tarif: \$19.90/Monat für 25,000 Requests.  [^10]
- Liefert Deeplinks, Untertitel-Sprachen, Ablaufdatum, Quality-Stufen.  [^11]


### 3. Watchmode API

51 Länder, 187 Provider, Deep-Links bis Episodenebene.  [^12][^13]

- Free-Tier: 1,000 Requests/Monat, jedoch nur US-Katalog.  [^14]
- Voller Globalzugriff erst ab „Pro“-Plan (\$249/Monat).  [^14]
- Gute ID-Zuordnung (IMDb, TMDb) und CSV-Mapping zum Download.  [^12]


### 4. Utelly API (via RapidAPI)

Universal-Such-Engine für weltweite Sender \& OTTs; 1,000 Calls/Monat kostenlos.  [^15]

- Stützt sich auf eigene Metadatenplattform.  [^16]
- Liefert Provider pro Region mit Deeplinks; IMDb-Suche verfügbar.  [^15]
- Höhere Limits \$99/Monat, Abdeckung kleiner als Watchmode/SA.


### 5. JustWatch (unofficial GraphQL)

JustWatch betreibt das größte Streaming-Verzeichnis (120 Länder).  [^17]

- Offizielle Partner-API nur mit Vertrag.  [^18]
- Für Hobby-Projekte existieren inoffizielle GraphQL-Wrappers (z.B. `simple-justwatch-python`) und Node-SDK `justwatch`; kostenlos, aber TOS-Risiko.  [^19][^20]
- IMDb-Links sind im Payload versteckt und können extrahiert werden.  [^21]


### 6. International Showtimes – Streaming API

AI-Crawler liefert Echtzeit-Verfügbarkeit, inklusive Preise \& Barrierefreiheitsdaten.  [^22]

- Keine öffentliche Preisangabe; Testzugang auf Anfrage.
- Bietet ID-Matching zu IMDb/TMDb.  [^22]
- Für rein private Nutzung oft Overkill.


### 7. Reelgood Partner API

Reelgood indiziert 100+ Dienste und bietet REST-API mit IMDb/EIDR-Mapping.  [^23][^24]

- API-Keys nur nach Kontakt; meist kostenpflichtig.  [^25]
- Starkes Popularitäts-Scoring, aber weniger freie Kontingente.


## Vergleichstabelle

| Anbieter | Länder­abdeckung | IDs unterstützt | Free-Quota | Kosten nächst­höherer Plan | Deeplinks | Bemerkung |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| TMDB WatchProviders | ≈180[^1] | TMDb, IMDb[^2] | unbegrenzt[^4] | – | Nein | Rein „wo zu sehen“, keine Preise[^5] |
| Streaming Availability | 60[^7] | IMDb, TMDb[^8] | 100/Tag[^9] | \$19.90/25,000 req[^10] | Ja[^11] | Vollständige Metadaten |
| Watchmode | 51[^12] | IMDb, TMDb[^12] | 1,000/Monat (US-only)[^14] | \$249/35,000 req[^14] | Ja[^12] | Episode-genau |
| Utelly | ~100[^16] | IMDb[^15] | 1,000/Monat[^15] | \$99/100,000 req[^15] | Ja[^15] | Gute Preisinfos |
| JustWatch (unofficial) | 120[^17] | Intern; IMDb extrahierbar[^21] | Unbegrenzt[^19] | n/a | Ja (inoffiziell)[^19] | TOS-Risiko |
| International Showtimes | 70+[^22] | IMDb, TMDb[^22] | Trial[^22] | Angebot auf Anfrage[^22] | Ja[^22] | Preis \& Accessibility |
| Reelgood | 140+[^23] | IMDb, EIDR[^23] | Trial[^23] | Angebot auf Anfrage[^23] | Ja[^23] | Popularitäts-Scores |

## Empfehlungen für Ihr Privatprojekt

1. **Schneller Einstieg, null Kosten:**
    - Nutzen Sie TMDB + Watch Providers für den Basis-Check, ob eine Serie in einem bestimmten Land verfügbar ist. Sie brauchen nur einen kostenlosen TMDb-Key, und dank `/find/{imdb_id}` ist kein Mapping-Aufwand nötig.  [^1][^2]
2. **Mehr Details \& Deep-Links bei kleinem Budget:**
    - Kombinieren Sie TMDB mit dem **Streaming Availability API**-Free-Tier. Damit erhalten Sie Deeplinks, Videoqualität und Ablaufdatum für 60 Länder mit 100 Aufrufen pro Tag. Für höhere Limits liegt die Monatsgebühr mit \$19.90 noch im Hobby-Budget.  [^10][^11][^9]
3. **Experimente \& Data-Mining:**
    - Falls Sie keine Sorge vor AGB-Kollisionen haben, liefert das inoffizielle JustWatch-GraphQL-Endpoint riesige Datenmengen gratis. Extrahieren Sie die `externalIds` für IMDb-Mappung; Beispiel-Regex siehe StackOverflow-Beitrag.  [^19][^21][^17]
4. **Region-Spezifische Preis-Analysen:**
    - Sobald Sie Miet-/Kaufpreise benötigen, testen Sie Utelly (1000 Calls/Monat frei).  [^15]

## Praxisbeispiel: „Better Call Saul“ auf Netflix Deutschland

```url
GET https://streaming-availability.p.rapidapi.com/shows/tt3032476?country=de
X-RapidAPI-Key: <IhrKey>
```

Antwortauszug (gekürzt):

```json
"streamingOptions": [{
  "service": "netflix",
  "type": "subscription",
  "link": "https://www.netflix.com/de/title/80021955",
  "quality": "HD"
}]
```

Damit können Sie direkt prüfen, ob die Serie (`tt3032476`) in Deutschland auf Netflix verfügbar ist und erhalten zusätzlich den Deeplink, den Monetarisierungstyp (Abo) und die Qualitätsstufe.[^8]

## Implementierungs-Workflow

### Schritt 1 – ID-Mapping

1. IMDb-ID der Serie aus Ihrer Datenquelle lesen.
2. Per TMDb-Endpoint `/find/{imdb_id}` die TMDb-ID holen (gratis).  [^2]
3. Diese TMDb-ID optional in lokale DB cachen, um Quoten zu sparen.

### Schritt 2 – Verfügbarkeits-Query

- **Minimalvariante:**
`/tv/{tmdb_id}/watch/providers` → Filter auf `results.DE` → liefert Array aller deutschen Dienste.  [^1]
- **Detailvariante:**
Streaming Availability API `/shows/{imdb_id}?country=de` → gibt Deep-Links, Audio-Spuren, Untertitel, Expiry.  [^11]


### Schritt 3 – Caching \& Ratenlimits

- Antworten 24 h zwischenspeichern; alle oben genannten Free-Tiers erlauben das (TMDb ausdrücklich gestattet lokale Caches).  [^4]
- Für Echtzeit-Daten (Preise) nur differenzielle Updates über „Changes“-Endpoint von Streaming Availability nutzen.  [^8]


### Schritt 4 – Anzeige im Frontend

- Service-Logo per URL aus API (z.B. `"logoPath":"/t2yyOv...", serviceColor:"#d81f26"` von Streaming Availability).  [^11]
- Region-Badge „DE“ daneben.
- Deeplink-Button, der den Nutzer direkt in die Netflix-App führt (Android/iOS-Schemes in Streaming Availability-Payload enthalten).  [^11]


## Wichtige Fallstricke

- **Netflix hat keine öffentliche API** – alle Dienste greifen über Aggregatoren wie JustWatch oder eigene Crawler zu.  [^26][^27]
- **JustWatch TOS**: Offizielle API nur mit Vertrag; inoffizielle Nutzung ist rechtlich unsicher.  [^18][^17]
- **Free-Tiers begrenzen Länder** – Watchmode liefert im Gratisplan nur den US-Katalog; prüfen Sie daher vorab, ob DE/AT in Ihrem Kontingent enthalten ist.  [^14]
- **Monetarisierungstyp-Filter** bei TMDb funktionieren nicht immer zuverlässig (siehe Coraline-Bug).  [^5]


## Zukunftssicherheit

- TMDb arbeitet laut Trello-Roadmap an erweiterten Watch-Provider-Endpunkten; halten Sie Ihr Mapping modular.  [^2]
- Streaming Availability hat in 2025 bereits 60 Länder; Roadmap sieht 80+ vor.  [^7]
- Sollten Free-Tiers verschwinden, lässt sich der monatliche Traffic durch aggressives Caching und Deduplikation (z.B. Hash auf JSON-Antwort) stark reduzieren.


## Fazit

Für ein privates, kostenbewusstes Projekt erfüllt die Kombination **TMDb + Streaming Availability API** alle Anforderungen: weltweite Abdeckung, IMDb-Lookup, Netflix Deutschland als Beispiel und ein dauerhaft kostenfreies Grundkontingent. Utelly oder Watchmode sind sinnvolle Ergänzungen, falls Sie Preise oder Episode-Deeplinks mit größerem Kontingent benötigen. Mit diesem Stack können Sie bereits heute einen zuverlässigen „Wo läuft meine Serie?“-Dienst aufbauen – ganz ohne das Budget eines Hollywood-Studios.

<div style="text-align: center">⁂</div>

[^1]: https://www.themoviedb.org/talk/643dbcf75f4b7304e2fe7f2a

[^2]: https://www.themoviedb.org/talk/5fe4f1c0136545003f5b3794

[^3]: https://www.themoviedb.org/talk/5ec15cc2d2147c0021b2386d

[^4]: https://www.themoviedb.org/talk/5cdcd9b59251416e32cfc9ac

[^5]: https://www.themoviedb.org/talk/644b8180596a91057957c085

[^6]: https://docs.movieofthenight.com

[^7]: https://rapidapi.com/movie-of-the-night-movie-of-the-night-default/api/streaming-availability

[^8]: https://docs.movieofthenight.com/guide/shows

[^9]: https://news.ycombinator.com/item?id=29862588

[^10]: https://rapidapi.com/movie-of-the-night-movie-of-the-night-default/api/streaming-availability/pricing

[^11]: https://github.com/movieofthenight/ts-streaming-availability

[^12]: https://api.watchmode.com

[^13]: https://api.watchmode.com/docs

[^14]: https://rapidapi.com/meteoric-llc-meteoric-llc-default/api/watchmode/pricing

[^15]: https://rapidapi.com/utelly/api/utelly/pricing

[^16]: https://www.softwareadvice.com/bi/utelly-profile/

[^17]: https://www.justwatch.com/de/JustWatch-Streaming-API

[^18]: https://apis.justwatch.com/docs/api/

[^19]: https://pypi.org/project/simple-justwatch-python-api/

[^20]: https://github.com/theabbie/justwatch

[^21]: https://stackoverflow.com/questions/77738952/how-to-scrape-imdb-id-link-from-justwatch

[^22]: https://www.internationalshowtimes.com/streaming-api

[^23]: https://data.reelgood.com/products/reelgood-partner-api/

[^24]: https://publicapis.io/reel-good-media-api

[^25]: https://github.com/ganeshnrao/reelgood-cli

[^26]: https://www.designgurus.io/answers/detail/is-there-any-api-for-netflix

[^27]: https://www.byteplus.com/en/topic/38825

[^28]: https://www.cloudwards.net/how-to-use-justwatch/

[^29]: https://www.themoviedb.org/talk/66e4926e9013fe872224395c

[^30]: https://rapidapi.com/apidojo/api/online-movie-database/pricing

[^31]: https://luisch.com/netflix-and-python/

[^32]: https://publicapis.io/watchmode-api

[^33]: https://apps.apple.com/us/app/watchmode/id1493844718

[^34]: https://support.justwatch.com/hc/en-us/articles/360020520297-Is-JustWatch-free

[^35]: https://github.com/prasanth-G24/Imdb_to_JustWatch

[^36]: https://www.themoviedb.org/talk/58a1e943c3a3683ebc000a54

[^37]: https://play.google.com/store/apps/details?id=com.justwatch.justwatch

[^38]: https://stadt-bremerhaven.de/justwatch-fuegt-listen-und-imdb-importfunktion-hinzu/

[^39]: https://www.themoviedb.org/talk/5fafd41ed55e4d003dcf6232

[^40]: https://rapidapi.com/examples/streaming-availability-app

[^41]: https://docs.tavily.com/documentation/api-credits

[^42]: https://packagist.org/packages/guidebox/guidebox-php

[^43]: https://news.ycombinator.com/item?id=29862637

[^44]: https://cloud.google.com/livestream/pricing

[^45]: https://docs.movieofthenight.com/guide/authorization

[^46]: https://www.npmjs.com/package/guidebox

[^47]: https://rapidapi.com/blog/streaming-availability-api-with-java-python-php-ruby-javascript-examples/

[^48]: https://do.ithistory.org/db/companies/guidebox

[^49]: https://docs.movieofthenight.com/resource/countries

[^50]: https://github.com/movieofthenight/go-streaming-availability

[^51]: https://itexus.com/netflix-api-exploring-data-integration-and-streaming-solutions/

[^52]: https://github.com/movieofthenight/streaming-availability-api

[^53]: https://www.npmjs.com/package/streaming-availability/v/2.0.0

[^54]: https://www.movieofthenight.com/about/api

[^55]: https://datarade.ai/search/products/netflix-apis

