# T-011 — SkyNomad access, search strategy, and data-fields research

**Project:** Paragliding Forecasts Bulgaria
**Research date:** 2026-07-28
**Task:** T-011 — Research SkyNomad forum access and data fields

## 1. Executive conclusion

T-011 is complete as a research spike. SkyNomad has useful evidence for the
project, but it is split across two technically and legally different surfaces:

1. [`www.skynomad.com`](https://www.skynomad.com/) is a live WordPress site
   containing public news and narrative flight reports. It exposes a working,
   unauthenticated WordPress REST API and a sitemap. This surface is suitable
   for low-volume discovery and corroboration, but its articles are not a
   complete per-flight database.
2. [`forum.skynomad.net`](https://forum.skynomad.net/) contains the old phpBB
   forum and the much more valuable
   [`/leonardo/`](https://forum.skynomad.net/leonardo/) GPS flight database.
   Current SkyNomad pages still link to Leonardo flight IDs from 2025, so it is
   not merely a historical URL.

The important blocker is that the forum/Leonardo host currently:

- returns a Cloudflare managed JavaScript/cookie challenge and HTTP `403` to a
  normal automated HTTP client before a flight page can be read;
- publishes a [`robots.txt`](https://forum.skynomad.net/robots.txt) with
  `Allow: /`, but also with the content signals `search=yes`,
  `ai-train=no`, and `use=reference`;
- publishes no numeric request quota or `Crawl-delay`;
- provides no verified public developer API, data licence, bulk export, or
  terms authorizing reuse of pilot flight data for model training.

Therefore, **a Leonardo scraper or an ML-training import must not be
implemented or scheduled yet**. `Allow: /` does not override the explicit
`ai-train=no` signal, unknown content rights, or the active technical
challenge. The correct next step is written permission from SkyNomad for the
specific project use, preferably accompanied by a supported export/API and an
approved rate.

The open-source [Leonardo XC Server repository][leo-repo] does, however, make
the likely data model, URL patterns, filters, internal endpoints, and HTML
structure sufficiently clear to design the future collector. Those findings
are documented below, but they are **candidate implementation details derived
from Leonardo source code**, not a verified contract for SkyNomad's deployed
version.

### Recommended source decision

| Surface                       | Use now                                              | Automated collection status                                                              | Project role                                                                         |
| ----------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| SkyNomad WordPress news       | Low-volume REST discovery and manual corroboration   | Technically viable; retain only short evidence and links until reuse terms are clarified | Find named locations, notable flights, dates, route descriptions, and Leonardo links |
| SkyNomad phpBB forum          | Manual browser inspection after Cloudflare challenge | Not approved; live structure and registration could not be verified                      | Narrative trip reports, competition posts, links, manual context                     |
| SkyNomad Leonardo list/detail | Manual validation only, after normal browser access  | **Blocked pending permission**                                                           | Primary candidate for structured flight facts                                        |
| IGC/KML downloads             | Do not automate                                      | **Blocked pending permission and live authorization test**                               | Highest-quality validation and coordinates if expressly allowed                      |
| Owner-provided export/API     | Request this first                                   | Preferred                                                                                | Safest source for T-013 and later ingestion                                          |

### T-013 fallback assessment

SkyNomad remains a plausible fallback for a **small manually validated
reference sample**, because:

- current WordPress posts link to specific Leonardo records;
- the archive contains named locations and notable 100+ km flights;
- the Leonardo platform is designed around flight IDs, takeoffs, distances,
  route types, coordinates, and track files.

It is **not currently cleared as a training-data fallback**. The forum host's
`ai-train=no` signal directly conflicts with using automatically collected
content to train or fine-tune a model. T-013 should use SkyNomad only if one of
these becomes true:

1. SkyNomad supplies or licenses an export for the stated purpose;
2. SkyNomad gives explicit written permission that supersedes the generic
   content signal for this project; or
3. the T-013 artifact is restricted to a non-training, manually cited
   reference/validation set and the product owner accepts that limitation.

## 2. Scope derived from the project documents

The following supplied documents were reviewed:

- `project-brief.md`;
- the current `handoff.md`;
- `tasks.md`;
- `architecture.md`;
- `decisions.md`;
- `T-010-xccontest-research-report.md`.

The requested project locations are:

- Sofia — Vitosha / Kominite;
- Zlatitsa;
- Sopot;
- Nevsha;
- Shumen;
- Pastrina;
- Dobrich region.

The first positive-flight dataset needs flights of at least 100 km, while
preserving separate 100+/200+/300+ km bands. Records need provenance and enough
information to join a flight to a project site and historical weather.

The handoff defines T-011 as research, not scraper implementation. It asks for:

- usable public forum, trip-report, competition, pilot, and downloadable-file
  sources;
- date, launch, distance, duration, route type, track/IGC link, source URL, and
  validation notes;
- search, indexing, and archive options;
- a policy decision between systematic discovery and manual/permission-based
  collection;
- confidence and provenance rules for sparse narrative records;
- an assessment of SkyNomad as a possible T-013 sample source.

Project boundaries retained by this report:

- T-009 owns authoritative site coordinates, aliases, and catchment radii;
- T-012 owns the persistence schema;
- ingestion belongs in the Python 3.12/`uv` batch side under `services/ml`;
- web and API request handlers must not scrape SkyNomad;
- raw external data stays outside Git;
- only sanitized, permitted fixtures may be committed under `data/samples`.

## 3. What SkyNomad actually contains

### 3.1 Public WordPress site

The current [`SkyNomad news archive`](https://www.skynomad.com/skynomad_news.htm)
contains articles from 2017 through 2025. It is useful because articles often
name:

- launch or flying region;
- approximate or exact distance;
- pilot;
- competition or training context;
- route description;
- direct Leonardo flight or filtered-track links.

Examples relevant to the project:

- [`August 2017`](https://www.skynomad.com/news/august-2017) states that Yasen
  Savov flew 360 km from Nevsha to Kavala and a 225 km FAI triangle. It links
  the SkyNomad Leonardo archive and also mentions Sopot and Shumen.
- [`September 2020`](https://www.skynomad.com/news/september-2020) describes
  repeated flights over 100 km and routes west of Sopot into the Zlatitsa
  valley.
- [`June–November 2021`](https://www.skynomad.com/news/june-november-2021)
  mentions flights from Pastrina and the Sopot region.
- [`Paragliding Easter: Borovets – Sopot`](https://www.skynomad.com/news/paragliding-easter-borovets-sopot)
  links specific Leonardo flight IDs `43067` and `43068`.
- [`January 2017`](https://www.skynomad.com/news/january-2017) links Leonardo
  flight `20846`.

These articles are good discovery evidence, but a sentence such as “flights of
over 100 km” does not identify individual flights, exact dates, duration,
coordinates, or track validity. Narrative pages should never be silently
converted into fully validated flight rows.

### 3.2 phpBB forum

Indexed references and SkyNomad's own links page identify the forum as a
Bulgarian forum and photo gallery. The current
[`SkyNomad paragliding links`](https://www.skynomad.com/bg/%D0%B2%D1%80%D1%8A%D0%B7%D0%BA%D0%B8-%D0%B7%D0%B0-%D0%BF%D0%B0%D1%80%D0%B0%D0%BF%D0%BB%D0%B0%D0%BD%D0%B5%D1%80%D0%B8%D0%B7%D1%8A%D0%BC)
page explicitly lists:

- the `skynomad.net` Bulgarian forum;
- the photo gallery;
- “Leonardo GPS flight tracks.”

The forum itself could contain trip reports, competition discussions, and
external track links. Its live topic structure, search form, login state, and
post selectors could not be verified because Cloudflare challenged every
forum-page request made by the research client.

Forum posts should be treated as unstructured supporting evidence. Even after
permission, they are not a reliable substitute for the Leonardo flight
database because:

- location and distance may appear only in prose;
- dates may refer to posting rather than flight date;
- links and attachments may be missing or expired;
- duplicate reports may describe the same flight;
- users may edit or delete posts.

### 3.3 Leonardo GPS flight database

SkyNomad's Leonardo instance is the important structured source. The
[Leonardo project itself lists “Bulgarian - Skynomad Leonardo”][leo-install]
among installations. SkyNomad's own current WordPress articles use URLs such
as:

```text
https://forum.skynomad.net/leonardo/flight/43067
https://forum.skynomad.net/leonardo/flight/43068
http://forum.skynomad.net/leonardo/flight/20846
```

The platform's source code shows records for:

- flight ID and canonical detail page;
- flight date and start/end time;
- duration;
- first and last coordinates;
- source takeoff ID and display name;
- straight/open distance;
- optimized/scored XC distance;
- route/scoring type;
- score;
- glider category/class;
- pilot identity;
- altitude/vario fields;
- IGC, KML/KMZ, and map-derived data;
- validation, comments, and photos depending on installation configuration.

This is the right data surface in principle. The uncertainty is access and
permission, not whether the underlying application was designed to hold the
needed fields.

## 4. Live access tests on 2026-07-28

### 4.1 Results

| Request                                                            | Observed result                              | Meaning                                          |
| ------------------------------------------------------------------ | -------------------------------------------- | ------------------------------------------------ |
| `GET https://www.skynomad.com/`                                    | `200`, HTML; advertises WordPress REST links | Public main site                                 |
| `GET https://www.skynomad.com/news/august-2017`                    | `200`, HTML; advertises post JSON            | Public narrative article                         |
| `GET https://www.skynomad.com/?rest_route=/wp/v2/posts&per_page=1` | `200`, JSON; `Allow: GET`; `X-WP-Total: 143` | Public REST collection confirmed                 |
| `GET https://www.skynomad.com/sitemap_index.xml`                   | `200`, Yoast sitemap index                   | Supported archive discovery                      |
| `GET https://www.skynomad.com/robots.txt`                          | `200`, plain text                            | Main-site crawl rules retrievable                |
| `GET https://forum.skynomad.net/`                                  | `403`, `cf-mitigated: challenge`             | Automated access challenged before forum content |
| `GET https://forum.skynomad.net/leonardo/`                         | `403`, `cf-mitigated: challenge`             | Same blocker for Leonardo                        |
| `GET https://forum.skynomad.net/leonardo/flight/43067`             | challenge rather than record content         | Live per-flight DOM/API not verifiable           |
| `GET https://forum.skynomad.net/robots.txt`                        | `200`, plain text                            | Policy is readable despite challenge             |

The challenge page says JavaScript and cookies must be enabled. Changing from a
named research user agent to a normal desktop-browser user agent did not change
the `403`. This is a technical anti-automation gate, not a published numeric
rate limit.

### 4.2 Important distinction

The following are **live-verified**:

- main-site WordPress REST access;
- current main-site links to recent Leonardo IDs;
- main-site and forum robots policies;
- Cloudflare challenge on the forum and Leonardo pages.

The following are **source-code-derived candidates**:

- Leonardo selectors;
- advanced-filter field names and encoded filter behavior;
- internal JSON/XML endpoints;
- detailed response fields;
- IGC authorization/captcha flow.

They must be checked against the deployed SkyNomad version before any collector
is built.

## 5. API and machine-readable access

### 5.1 Supported public API on `www.skynomad.com`

The main site advertises the standard WordPress REST API:

```text
GET https://www.skynomad.com/wp-json/wp/v2/posts
```

The query-route equivalent was verified successfully and may work more
reliably through restrictive proxies:

```text
GET https://www.skynomad.com/?rest_route=/wp/v2/posts
```

A focused discovery request would be:

```text
GET /?rest_route=/wp/v2/posts
    &search=Nevsha
    &per_page=100
    &page=1
    &_fields=id,date,date_gmt,modified_gmt,slug,link,title,content,excerpt,categories,tags
```

The official [WordPress Posts API documentation][wp-posts] defines:

- `search`;
- `after`, `before`, `modified_after`, and `modified_before`;
- `page` and `per_page`;
- ordering and taxonomy filters;
- the post fields used above.

WordPress caps `per_page` at 100 and returns `X-WP-Total` and
`X-WP-TotalPages`, as described by the official
[pagination documentation][wp-pagination]. That is a response-size limit, not
a site request-rate quota.

The archive contained 143 public posts at research time. Exact REST full-text
search totals for the current project aliases were:

| Search term | Matching posts |
| ----------- | -------------: |
| `Nevsha`    |              2 |
| `Sopot`     |             25 |
| `Zlatitsa`  |              1 |
| `Shumen`    |              2 |
| `Pastrina`  |              1 |
| `Dobrich`   |              0 |
| `Vitosha`   |              0 |
| `Kominite`  |              0 |

These are not flight counts. They show only that narrative discovery is useful
for some locations and insufficient for others. Bulgarian spellings,
transliterations, nearby towns, takeoff names, and route landmarks must be
added from T-009.

### 5.2 Does Leonardo have an API?

No documented, supported SkyNomad developer API was found.

The open-source Leonardo application contains internal machine-readable
endpoints in [`EXT_flight.php`][leo-ext-flight]. They include:

- `op=list_flights_json`;
- `op=flight_info`;
- `op=find_flights`;
- `op=list_flights`;
- other map/task helpers.

The most interesting candidate is conceptually:

```text
GET /leonardo/EXT_flight.php
    ?op=list_flights_json
    &lat=<launch-lat>
    &lon=<launch-lon>
    &distance=<radius-km>
    &tm1=<unix-start>
    &tm2=<unix-end>
    &count=<limit>
```

The source shows:

- a default radius of 100 km;
- a radius cap of 2,500 km;
- a default result count of an installation setting or 50;
- date filtering by timestamps or `date=dd.mm.yyyy`;
- ordering by flight score unless a date/start-time matching mode is used;
- output wrapped in `{ "flights": [...] }`.

However, this endpoint must **not** be treated as the recommended API yet:

1. It is not documented by SkyNomad as a stable public interface.
2. Live routing, parameter names, response encoding, authentication, and
   Cloudflare behavior could not be verified.
3. The source emits JSON-looking data with `Content-Type: text/html`, and some
   values contain pre-rendered HTML rather than typed JSON.
4. The source has a likely bug: it reads `$_REQUEST['$takeoffID']` with a dollar
   sign in the key.
5. Most importantly, the inspected `list_flights_json` branch starts with a
   broad `WHERE 1` and does not visibly add `private=0`, unlike another nearby
   XML query. The deployed version may differ, but this is a privacy risk.
   **Do not call or enumerate this endpoint until SkyNomad confirms that it is
   supported and returns only public records.**

The correct permission request should therefore ask first for an owner-provided
export or supported endpoint, rather than asking only for permission to scrape
HTML.

### 5.3 Candidate Leonardo URL patterns

The application's rewrite configuration defines these URL shapes
([source][leo-routes]):

```text
/leonardo/flight/<flightID>
/leonardo/flight/<flightID>/igc/
/leonardo/flight/<flightID>/kml/
/leonardo/takeoff/<waypointID>
/leonardo/tracks/<country>/<date>/<seo-filter-segment>
```

The list filter segment can contain values such as:

```text
brand:all,cat:1,class:all,xctype:all,club:all,pilot:all,takeoff:<sourceTakeoffID>
```

SkyNomad's 2017 article provides a real filtered-track example using
`tracks/world/alltimes/...`. Distance/date rules added through the advanced
filter are represented by an opaque `fltr` value rather than a readable,
stable query contract.

Non-SEO deployments can use query-style URLs such as:

```text
index.php?op=show_flight&flightID=<id>
index.php?op=list_flights&page_num=<n>
```

The deployed SkyNomad links confirm SEO flight routes, but not every route or
filter behavior.

## 6. How flights are searched for the exact project locations

SkyNomad is not best understood as seven fixed categories matching the project
locations.

### 6.1 Preferred model: source takeoff IDs

Leonardo's user-facing flight list is organized by:

- country and date/season;
- takeoff waypoint;
- pilot;
- glider category/class;
- route/scoring type;
- distance and score filters.

The advanced filter source defines:

- `FILTER_takeoffs_incl` — one or more source takeoff IDs;
- `FILTER_cat` — glider-category bitmask;
- `FILTER_olc_type` — route type;
- `FILTER_linear_distance_select` — straight/open distance;
- `FILTER_olc_distance_select` — optimized XC distance;
- date range and duration filters.

Relevant exact values from the Leonardo source are:

| Concept                 | Value                                 |
| ----------------------- | ------------------------------------- |
| Paraglider              | glider-category bit `1`               |
| Hang glider, flex wing  | bit `2`                               |
| Hang glider, rigid wing | bit `4`                               |
| Sailplane/glider        | bit `8`                               |
| Free flight             | route code `1`, token `FREE_FLIGHT`   |
| Free triangle           | route code `2`, token `FREE_TRIANGLE` |
| FAI triangle            | route code `4`, token `FAI_TRIANGLE`  |

The correct project workflow is:

1. Use T-009's canonical coordinates and alias list.
2. In a normal browser, identify every SkyNomad/Leonardo takeoff waypoint that
   belongs to each project site or catchment.
3. Record the source waypoint ID, displayed name, URL, coordinates, and
   mapping evidence.
4. Filter for `cat=1` and optimized XC distance of at least 100 km.
5. Apply an explicit historical date range.
6. Page through results, preserving flight ID and canonical detail URL.
7. Map each source takeoff ID to the T-009 canonical site ID. Do not map by
   loose text alone when a source ID is available.

This makes the location strategy a **source-takeoff mapping problem**, not only
a text-search problem.

### 6.2 Coordinate-and-radius discovery

The source-derived `list_flights_json` route appears able to filter on the
first recorded latitude/longitude within a radius. This would align well with
T-009 catchment geometry and is particularly useful for:

- Dobrich as a broad region;
- multiple nearby flatland starts around Nevsha or Shumen;
- takeoff names that do not match project aliases;
- records attached to an “unknown” or approximate waypoint.

It is not yet approved because:

- it is an internal endpoint;
- its live privacy behavior is unverified;
- the code uses legacy coordinate conventions in different paths;
- it is behind the same Cloudflare challenge;
- the robots content signal blocks AI training.

Use it only if SkyNomad names it as a supported public-data interface or
provides an equivalent export.

### 6.3 WordPress narrative discovery

Use WordPress full-text search with all aliases, for example:

- `Nevsha`, `Невша`;
- `Shumen`, `Шумен`;
- `Pastrina`, `Пъстрина`, `Montana`, `Монтана`;
- `Zlatitsa`, `Златица`;
- `Vitosha`, `Витоша`, `Kominite`, `Комините`, `Sofia`, `София`;
- `Dobrich`, `Добрич`, and T-009's nearby takeoff/settlement aliases;
- `Sopot`, `Сопот`, nearby ridge and valley names.

Also search for evidence words such as `km`, `record`, `XC`, `triangle`,
`tracklog`, `Leonardo`, and competition names.

This method finds candidate stories, not all flights. Zero WordPress matches
for Dobrich, Vitosha, or Kominite must not be interpreted as zero qualifying
flights.

### 6.4 Forum discovery

If manual browser access succeeds:

1. use the forum's own search for exact aliases and Bulgarian spellings;
2. constrain by date where possible;
3. search competition/trip-report forums before general chat;
4. capture the canonical topic/post URL;
5. follow only user-visible track/Leonardo links;
6. deduplicate the result against the Leonardo flight ID.

Do not spider sequential topic IDs or scrape user profiles merely because URL
patterns make enumeration possible.

## 7. Exact candidate selectors and response fields

### 7.1 WordPress: use JSON, not HTML scraping

For public news posts, prefer the REST response:

| JSON path                 | Meaning                    |
| ------------------------- | -------------------------- |
| `id`                      | WordPress post ID          |
| `date` / `date_gmt`       | publication time           |
| `modified_gmt`            | incremental checkpoint     |
| `slug`                    | stable readable identifier |
| `link`                    | canonical article URL      |
| `title.rendered`          | title                      |
| `content.rendered`        | article HTML               |
| `excerpt.rendered`        | short excerpt              |
| `categories[]` / `tags[]` | discovery metadata         |

Extract links from `content.rendered` and normalize tracking parameters such as
`fbclid` away from the canonical Leonardo URL.

If an HTML fallback is ever needed, these selectors were verified on the live
`August 2017` article:

| Field                    | Live selector                                           |
| ------------------------ | ------------------------------------------------------- |
| Title                    | `h1.page-title.entry-title`                             |
| Publication timestamp    | `time.entry-date[datetime]`                             |
| Author                   | `.entry-meta .author.vcard`                             |
| Article body             | `.entry-content`                                        |
| Leonardo links           | `.entry-content a[href*="forum.skynomad.net/leonardo"]` |
| Category/footer metadata | `footer.entry-utility`, `.cat-links`                    |

### 7.2 Leonardo flight-list selectors

The following selectors are derived from
[`GUI_list_flights.php`][leo-list], not verified against SkyNomad's live DOM:

| Field                         | Candidate selector or rule                                                                         |
| ----------------------------- | -------------------------------------------------------------------------------------------------- |
| Flights table                 | `table.listTable`                                                                                  |
| Data row                      | `table.listTable tr[id^="row_"]`                                                                   |
| Flight ID                     | parse integer from row `id="row_<flightID>"`; verify against detail link                           |
| Alternating row class         | `.l_row1` or `.l_row2`; do not depend on it                                                        |
| First row for a date          | `.newDate`                                                                                         |
| Date cell                     | `td.dateString`                                                                                    |
| Repeated/visually hidden date | `td.dateString .dateHidden`                                                                        |
| Pilot/takeoff combined cell   | `td.pilotTakeoffCell`                                                                              |
| Pilot                         | `td.pilotTakeoffCell .pilotLink`                                                                   |
| Takeoff                       | `td.pilotTakeoffCell .takeoffLink a[id^="t_"]`                                                     |
| Duration                      | the column mapped to the localized Duration header; positional fallback `td.pilotTakeoffCell + td` |
| Distance cells                | `td.distance`, but resolve semantics from header                                                   |
| Score and route-type icon     | `td.OLCScore`; inspect child image `title`/`alt`                                                   |
| Detail URL                    | `a.flightLink[href]`                                                                               |
| Page                          | `page_num=<n>` in generated pagination links                                                       |

**Critical parser rule:** do not assume that “the first `.distance` cell” has
one fixed meaning. The source can configure the column before OLC distance as
either straight distance or speed. Build a localized header map from the table
header:

- date;
- pilot;
- takeoff;
- duration;
- straight distance or mean speed;
- OLC/XC distance;
- OLC score.

If required headers cannot be mapped, fail the page instead of shifting values
into the wrong fields.

### 7.3 Candidate internal `list_flights_json` fields

The source-derived response contains string values:

```text
flightID
date
firstLat
firstLon
lastLat
lastLon
DURATION
START_TIME
END_TIME
MAX_ALT
MAX_VARIO
linearDistance
olcDistance
olcScore
scoreSpeed
olcScoreType
gliderBrandImg
gliderCat
categoryImg
pilotName
takeoff
```

Caveats:

- numeric values may already include localized units or formatting;
- `olcScoreType`, glider brand/category, and class may contain HTML image
  fragments;
- no source takeoff ID is included in the listed output, despite a displayed
  takeoff name;
- the response content type is HTML;
- live availability and private-record exclusion are unverified.

This endpoint would need a strict adapter and validation suite even with
permission.

### 7.4 Detail fields

The source-derived `flight_info` output and detail page can expose:

- flight ID and date;
- first/last coordinates;
- takeoff and landing coordinates;
- time-zone offset;
- duration and start/end time;
- task/route geometry and map bounds;
- optimized task/score fields;
- photos;
- pilot name;
- takeoff ID and name;
- KMZ URL.

The inspected source appears malformed around the final `takeoffID`/`takeoff`
string concatenation, which is another reason not to assume a stable JSON
contract.

For HTML detail pages, extract by normalized field label and its adjacent value
rather than by row number. The source shows labels for:

- OLC score type;
- OLC/XC distance;
- OLC score;
- open/straight distance;
- maximum distance;
- takeoff location and time;
- duration;
- landing location and time;
- validation status.

## 8. Recommended normalized flight contract

T-012 still owns the storage schema. The following is the T-011 extraction
contract that T-012 should be able to represent.

| Normalized field             | Type         | Source and normalization                                       | Requirement                        |
| ---------------------------- | ------------ | -------------------------------------------------------------- | ---------------------------------- |
| `source_system`              | enum/text    | `skynomad_leonardo` or `skynomad_news`                         | Required                           |
| `source_flight_id`           | integer/text | Leonardo row/detail ID; null for narrative-only lead           | Required for validated flight      |
| `source_url`                 | URL          | Canonical HTTPS detail/article URL; strip tracking params      | Required                           |
| `source_takeoff_id`          | text         | Leonardo waypoint ID                                           | Strongly preferred                 |
| `source_takeoff_name_raw`    | text         | Preserve source spelling before T-009 mapping                  | Required when present              |
| `project_site_id`            | FK/text      | T-009 canonical site/region                                    | Required before training           |
| `site_match_method`          | enum         | `takeoff_id`, `start_radius`, `manual_route`, `narrative_only` | Required                           |
| `site_match_distance_km`     | decimal      | Distance from first point to canonical site/catchment          | When coordinate-matched            |
| `flight_date_local`          | date         | Flight date, not post date                                     | Required                           |
| `source_timezone`            | text/offset  | Preserve raw offset/unknown state                              | Required metadata                  |
| `start_time_local`           | time/null    | Leonardo start time                                            | Optional                           |
| `end_time_local`             | time/null    | Leonardo end time                                              | Optional                           |
| `duration_seconds`           | integer/null | Parse duration once; retain raw value                          | Preferred                          |
| `start_lat`, `start_lon`     | decimal/null | First track point; validate sign against map                   | Strongly preferred                 |
| `landing_lat`, `landing_lon` | decimal/null | Last point/landing                                             | Preferred                          |
| `distance_optimized_km`      | decimal      | Leonardo `FLIGHT_KM` / displayed OLC distance                  | Required for project distance band |
| `distance_linear_km`         | decimal/null | Leonardo `LINEAR_DISTANCE`; do not substitute silently         | Optional                           |
| `distance_raw`               | text         | Original display value and unit                                | Required provenance                |
| `distance_band`              | enum         | `100_199`, `200_299`, `300_plus`; derive from selected metric  | Required                           |
| `route_type`                 | enum         | `free_flight`, `free_triangle`, `fai_triangle`, `unknown`      | Preferred                          |
| `glider_category`            | enum         | Keep only paraglider bit/category `1` for this dataset         | Required                           |
| `pilot_name_raw`             | text/null    | Collect only if permission allows; not needed as ML feature    | Optional/restricted                |
| `track_detail_url`           | URL/null     | Flight page                                                    | Preferred                          |
| `igc_url`, `kml_url`         | URL/null     | Link only until download/reuse is expressly allowed            | Optional/restricted                |
| `track_available`            | boolean      | Link/button exists, not “successfully downloaded”              | Preferred                          |
| `source_validation_raw`      | text/null    | Leonardo validation indicator                                  | Preferred                          |
| `narrative_evidence`         | text/null    | Short paraphrase, not copied full article/post                 | Supporting                         |
| `discovery_source_url`       | URL/null     | WordPress/forum page that led to flight                        | Supporting                         |
| `validation_status`          | enum         | Rules below                                                    | Required                           |
| `validation_notes`           | text         | Contradictions, missing fields, manual checks                  | Required                           |
| `fetched_at`                 | timestamp    | Provenance                                                     | Required                           |
| `permission_basis`           | text         | Written approval/export/version or reference-only              | Required                           |
| `raw_artifact_hash`          | hash/null    | Hash of permitted raw response kept outside Git                | Preferred                          |

### Distance decision

Leonardo distinguishes:

- `LINEAR_DISTANCE` — straight/open distance;
- `FLIGHT_KM` — optimized/scored XC distance;
- `MAX_LINEAR_DISTANCE` — another maximum-distance measure on detail views.

For continuity with scored XC records and route types, this report recommends
using `FLIGHT_KM`/OLC distance for the 100/200/300 km project bands, while
preserving the other distances separately. The product owner and T-012 must
confirm this before T-013 labels are frozen.

### Coordinate decision

Legacy Leonardo paths do not use longitude consistently in every helper. A
parser must:

1. preserve raw values;
2. parse to decimal degrees;
3. check Bulgaria bounds;
4. compare the first point with the displayed takeoff;
5. inspect the rendered map for a manual sample;
6. reject or quarantine sign-swapped records.

## 9. Validation, provenance, and confidence rules

### 9.1 Validation states

| State                   | Minimum evidence                                                                                                             | Allowed use                           |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `lead`                  | Narrative mention, search result, or article without a unique flight ID                                                      | Discovery queue only                  |
| `identified`            | Unique Leonardo flight ID and canonical URL, but detail fields unavailable                                                   | Manual follow-up; no training         |
| `structured_unverified` | Parsed public fields with source ID, date, takeoff, distance, and category; no track/manual cross-check                      | QA queue                              |
| `validated_metadata`    | Required fields pass type/range checks and a human verifies page/map/takeoff mapping                                         | Descriptive analysis if licensed      |
| `validated_track`       | Above plus permitted IGC/KML parse matching ID/date/start/duration/distance within tolerances                                | Highest-confidence sample if licensed |
| `rejected`              | Wrong sport/category, under 100 km, duplicate, inconsistent date/location, private/restricted record, or unresolved conflict | Exclude                               |

### 9.2 Confidence rules for narrative records

- Exact distance + exact route + unique Leonardo link: high discovery
  confidence, but still not structured validation until the linked record is
  inspected.
- Exact distance + named launch but no unique record: medium-confidence lead.
- “100+ km flights” or a region named in a monthly summary: low-confidence
  lead; do not create individual flight rows.
- Competition task distance is not automatically a pilot's completed flight
  distance.
- Article publication date is not automatically the flight date.
- A pilot's name must not be used as a model feature and should be omitted or
  pseudonymized unless needed for deduplication and permitted.
- A broken track link does not invalidate a narrative claim, but caps the
  record below `validated_track`.
- SkyNomad non-coverage is not a negative example. Missing uploads and
  self-selection create strong bias.

### 9.3 Cross-checks

For every candidate validated record:

1. flight ID in row, detail URL, and structured response must agree;
2. date must be a plausible flight date and not merely post/submission date;
3. paraglider category must be `1`;
4. selected distance must be at least 100 km;
5. start point or source takeoff ID must map to a T-009 site/catchment;
6. route-type value and icon/label must agree;
7. duration must be positive and plausible;
8. coordinates must be within valid ranges and visually plausible;
9. duplicated bilingual articles must point to one flight, not two;
10. private, disabled, or locked records must not be collected.

## 10. IGC/KML access and registration

### 10.1 Track downloads

The Leonardo route configuration supports IGC/KML URLs, but the source
download flow checks whether:

- the flight belongs to the current user;
- the user is a moderator;
- the client IP is permitted to download IGC files;
- or a session/captcha condition has been satisfied.

If not authorized, the source renders a captcha-based IGC download form
([source][leo-igc]).

Implications:

- do not automate, solve, or bypass a captcha;
- do not assume that a visible IGC link grants bulk-download rights;
- do not redistribute IGC files merely because the Leonardo program code is
  GPL;
- ask SkyNomad whether the project may download, retain, derive features from,
  and redistribute any track data;
- if only metadata is licensed, store the canonical track URL and
  `track_available`, not the file.

The [Leonardo source header's GPL notice][leo-license] applies to the application
source code. It does **not** license SkyNomad users' flight records, forum
posts, photos, or IGC tracks.

### 10.2 Registration status

The live registration page could not be reached beyond the Cloudflare
challenge, so this report cannot confirm:

- whether new forum accounts are still accepted;
- whether email activation or moderator approval is required;
- whether Leonardo uses the same account;
- whether a signed-in user sees additional fields or downloads;
- the current registration terms;
- whether any fee exists.

No evidence of a paid forum-membership requirement was found. phpBB
registration is normally free, but that general expectation is **not evidence
about the current SkyNomad deployment**. Treat cost as unknown until checked.
The WordPress `my-account`/shop account is a separate surface and should not be
confused with forum/Leonardo registration.

## 11. Manual verification instructions for the project owner

Use a normal personal browser. Do not use automation to defeat the Cloudflare
challenge.

### 11.1 Access and registration

1. Open [`https://forum.skynomad.net/`](https://forum.skynomad.net/).
2. Enable JavaScript and cookies for the Cloudflare human check.
3. Record whether the forum home page becomes public after the check.
4. Look for `Register`, `Регистрация`, or a user-control-panel link.
5. Before registering, capture:
   - the registration URL;
   - current terms and privacy links;
   - required fields;
   - email verification/moderator approval;
   - any fee or club-membership condition.
6. Do not create an account if accepting the terms would be inappropriate for
   organizational use. Instead, contact SkyNomad.
7. Open [`https://forum.skynomad.net/leonardo/`](https://forum.skynomad.net/leonardo/)
   while signed out and, if an account was legitimately created, while signed
   in. Record the difference.

### 11.2 Known flight-page checks

Open these without their Facebook tracking parameters:

```text
https://forum.skynomad.net/leonardo/flight/43067
https://forum.skynomad.net/leonardo/flight/43068
http://forum.skynomad.net/leonardo/flight/41125
http://forum.skynomad.net/leonardo/flight/20846
```

For each accessible page, record:

- final HTTPS URL and HTTP-visible error if any;
- whether login is required;
- flight date;
- pilot visibility;
- takeoff name and linked waypoint ID;
- start/landing coordinates;
- straight, maximum, and OLC/XC distances;
- route type;
- duration;
- paraglider category/class;
- validation flag;
- IGC/KML availability;
- whether download triggers login, captcha, or a direct file.

### 11.3 Search/filter check

1. Find `Flights`, `Tracks`, or `Advanced filter`.
2. Choose one year and the paraglider category only.
3. Add a minimum OLC/XC distance of 100 km.
4. Search the takeoff picker for one project alias.
5. Record the displayed takeoff name, source ID, URL, coordinates, and nearby
   variants.
6. Apply the filter and copy the complete resulting URL, including `fltr`.
7. Confirm pagination and whether repeated dates use hidden text.
8. Repeat with a second takeoff and a 200 km threshold.
9. Check whether a coordinate/radius map search is exposed in the UI. Do not
   call hidden endpoints merely because developer tools reveal them.

### 11.4 DevTools network check

Only while manually using visible features:

1. Open Developer Tools → Network.
2. Enable “Preserve log”.
3. Reload the flight list and one detail page.
4. Filter for `XHR`, `fetch`, `EXT_flight.php`,
   `GUI_EXT_flight_info.php`, `flight_info`, and `list_flights_json`.
5. Record request URL, method, status, content type, and field names.
6. Confirm whether responses exclude private/locked records.
7. Export a HAR **after removing cookies, authorization headers, account
   identifiers, and Cloudflare tokens**.

The sanitized HAR or screenshots would allow T-013 to replace candidate
selectors with verified ones.

## 12. Robots, rate limits, and policy decision

### 12.1 Forum/Leonardo robots policy

At research time, the forum
[`robots.txt`](https://forum.skynomad.net/robots.txt):

- allowed the wildcard user agent to crawl paths;
- contained no `Crawl-delay`;
- allowed search indexing;
- prohibited AI training;
- requested reference-level use;
- disallowed several named AI crawlers from the whole host.

Cloudflare explains that its
[content signals][cloudflare-content-signals] express site-owner preferences
for search, AI input, and AI training. Its 2026
[`use` signal documentation][cloudflare-use-signal] defines `reference` as the
index/excerpt/backlink level, rather than full reuse.

For this project:

- search-engine-style discovery and short cited references are consistent with
  the published signal;
- copying a systematic flight corpus into an ML-training dataset is not;
- full raw-page or track retention is not established as permitted;
- a written project-specific licence is required before training use.

### 12.2 Main-site robots policy

The main-site [`robots.txt`](https://www.skynomad.com/robots.txt) disallows:

- WooCommerce log/transient/upload directories;
- add-to-cart query variants;
- `/wp-admin/`, except `/wp-admin/admin-ajax.php`.

It points to the Yoast sitemap and does not disallow public posts or the REST
post collection. It contained no `Crawl-delay` or numeric rate limit. This
makes the REST API the technically preferred discovery route, but it does not
create a data-reuse licence.

### 12.3 Numeric limits actually found

| Limit                                             |                      Value | What it is                                          |
| ------------------------------------------------- | -------------------------: | --------------------------------------------------- |
| WordPress `per_page`                              |                        100 | Standard response-page maximum, not requests/minute |
| Current WordPress public post count               |                        143 | Archive size observed on 2026-07-28                 |
| Leonardo source `list_flights_json` default count | installation setting or 50 | Candidate endpoint response limit                   |
| Leonardo source radius default                    |                     100 km | Candidate query parameter default                   |
| Leonardo source radius maximum                    |                   2,500 km | Candidate parameter cap                             |
| Published crawl delay                             |                 None found | **Not permission for high-rate access**             |
| Published requests/minute/day                     |                 None found | Must be requested from owner                        |

No load test was performed and none should be performed to infer hidden
thresholds. The first automated Leonardo page request already received a
challenge.

### 12.4 Conservative operational proposal to ask SkyNomad to approve

This is a proposal, not an existing entitlement:

- one identified client;
- concurrency `1`;
- at least 10 seconds between Leonardo requests;
- cached responses never refetched within the same run;
- one historical backfill, then at most one weekly incremental run;
- a 14-day overlap for delayed uploads;
- maximum 100 Leonardo requests per run until the owner specifies otherwise;
- immediate stop on `401`, `403`, `429`, challenge, captcha, or changed
  `robots.txt`;
- honor `Retry-After`; exponential backoff with jitter for `429`/`503`;
- no browser automation, rotating identities, proxy rotation, or challenge
  bypass;
- no private/locked/profile enumeration;
- no IGC download unless separately approved.

The owner-specified policy must replace these numbers.

## 13. Proposed future collector and how it would run

No collector was implemented in T-011. If permission is obtained, the
recommended T-013/T-014 design is:

```text
services/ml/ingestion/skynomad/
  client.py          # approved HTTP/export client
  wordpress.py       # REST discovery
  leonardo_list.py   # list parser or supported API adapter
  leonardo_detail.py # detail adapter
  normalize.py       # typed field normalization
  location_map.py    # T-009 source-takeoff/catchment mapping
  validate.py        # field, coordinate, category, and distance checks
  checkpoint.py      # pages, dates, ETags/hashes
```

### 13.1 Source order

1. **Owner export/API** — preferred.
2. **WordPress REST API** — candidate discovery links and narrative evidence.
3. **Approved Leonardo list/detail access** — structured metadata.
4. **Approved IGC/KML access** — validation only where explicitly licensed.
5. **Manual review queue** — sparse or conflicting records.

### 13.2 Proposed command contract

The following is a design target, not an existing command:

```bash
uv run python -m services.ml.ingestion.skynomad \
  --mode backfill \
  --site nevsha \
  --from 2010-01-01 \
  --to 2026-07-28 \
  --min-olc-km 100 \
  --dry-run
```

After review:

```bash
uv run python -m services.ml.ingestion.skynomad \
  --mode incremental \
  --all-sites \
  --checkpoint var/skynomad/checkpoint.json
```

The real implementation should refuse to start unless configuration includes:

- a reviewed permission reference/version;
- approved endpoints;
- rate/concurrency limits;
- a user-agent contact;
- the current T-009 takeoff mapping;
- raw-retention and deletion rules.

### 13.3 Per-run behavior

1. Fetch and compare both robots policies.
2. Stop if the forum signals or relevant rules changed.
3. Load T-009 site aliases, coordinates, catchments, and source takeoff IDs.
4. Query the WordPress API incrementally by `modified_after`.
5. Discover and canonicalize Leonardo links.
6. If authorized, fetch filtered Leonardo pages/export segments.
7. Parse with a header map, not positional guesses.
8. Normalize both optimized and linear distances.
9. Restrict to paraglider records and calculate distance band.
10. Validate site mapping, date, coordinates, duration, and route type.
11. Deduplicate by `(source_system, source_flight_id)`.
12. Store raw permitted artifacts outside Git and hash them.
13. Emit a review queue for narrative-only and conflicting records.
14. Produce counts for seen, accepted, rejected, changed, and blocked records.
15. Update the checkpoint only after the run succeeds atomically.

### 13.4 Scheduling decision

Current decision: **do not schedule Leonardo collection**.

If SkyNomad approves the proposal:

- perform one bounded historical backfill by source takeoff ID;
- start with Nevsha, Shumen, and Sopot because the public archive already
  demonstrates relevant records;
- handle Dobrich as a T-009 region/multiple-takeoff mapping;
- run an incremental collection weekly during the flying season;
- use a two-week lookback to capture late uploads;
- keep WordPress discovery monthly or `modified_after`-based because the archive
  changes slowly.

## 14. Permission request

The [`SkyNomad contact page`](https://www.skynomad.com/contact) provides a
contact form and identifies SkyNomad Sport Club in Sopot. The request should
state the intended commercial/research use rather than asking vaguely whether
“scraping is allowed.”

Suggested questions:

1. May the project collect public Leonardo flight metadata for the named
   Bulgarian launch regions?
2. May those data be used to train, evaluate, and operate a commercial
   probability/ranking model?
3. Is there a supported API, database export, CSV, or administrator-generated
   sample?
4. Which fields and records are public, and how are private/locked flights
   excluded?
5. May IGC/KML files be downloaded and retained? May derived features be kept?
6. May pilot names be stored, or should they be omitted/pseudonymized?
7. What attribution and source links are required?
8. What request rate, concurrency, schedule, and user agent are acceptable?
9. Does permission cover historical backfill and later incremental updates?
10. What is the process for corrections, deletion requests, and revocation?
11. Does the current `ai-train=no,use=reference` policy intentionally cover
    this database, and can SkyNomad grant a project-specific exception?

Preferred written outcome:

- named permitted endpoints/export;
- exact permitted fields and purpose;
- rate and schedule;
- retention and redistribution terms;
- attribution;
- privacy/removal procedure;
- effective date and contact.

## 15. Open questions and limitations

1. **ML permission:** does SkyNomad grant a project-specific exception to
   `ai-train=no`?
2. **Live access:** can a normal browser consistently pass the Cloudflare
   challenge, or is an account/IP allowlist required?
3. **Registration:** is forum registration open, free, email-activated, or
   moderator-approved?
4. **Supported API/export:** which machine-readable interface is intended for
   third parties?
5. **Privacy:** does any internal endpoint expose private/locked records?
6. **Live version:** which Leonardo commit/fork is deployed, and do the
   candidate selectors/fields still match?
7. **Exact takeoff IDs:** what are the deployed source IDs for every T-009 site
   and nearby alias?
8. **Distance definition:** will the product label from optimized `FLIGHT_KM`
   or straight/open distance?
9. **Coordinate convention:** are longitudes standard signed decimal degrees in
   every live response?
10. **Time zone:** does the flight date/time carry a reliable source time zone,
    and how are daylight-saving transitions represented?
11. **IGC rights:** may tracks be downloaded, retained, parsed, and used for
    derived features?
12. **Rate limits:** no official numeric rate or crawl delay was found.
13. **Completeness:** how many uploads are missing, private, duplicated, or
    attributed to approximate takeoffs?
14. **Bias:** uploaded successful flights are self-selected positives; absence
    is not a true negative.
15. **Forum content:** exact topic selectors, attachments, and search behavior
    remain unverified.
16. **Terms/licence:** no public licence for forum posts or flight data was
    found. The visible “common conditions” page concerns tandem-service
    customers, not dataset reuse.
17. **Current flight detail:** the research environment could not directly read
    the contents of flight `43067`, `43068`, `41125`, or `20846`; it could only
    verify the links and the challenge.

## 16. T-011 acceptance summary

| T-011 requirement                | Result                                                                                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Identify usable SkyNomad sources | WordPress news, phpBB narrative forum, Leonardo flight DB, linked IGC/KML, and owner export/API identified                                       |
| Determine access method          | WordPress REST is live; forum/Leonardo automation is challenged and requires permission                                                          |
| Determine search strategy        | Source takeoff IDs + PG + minimum optimized distance + date; coordinate-radius only via approved endpoint; WordPress/forum aliases for discovery |
| Determine fields                 | Candidate list/detail/API fields and normalized contract documented                                                                              |
| Determine selectors              | Live WordPress selectors and source-derived Leonardo selectors documented separately                                                             |
| Check robots/rate limits         | Both robots files checked; forum content signals and Cloudflare challenge documented; no numeric rate found                                      |
| Check registration/manual needs  | Registration remains unverified; exact manual procedure supplied                                                                                 |
| Define validation/confidence     | Lead-to-track validation states and provenance rules supplied                                                                                    |
| Assess T-013 fallback            | Reference sample plausible; training use blocked until permission                                                                                |
| Implement scraper                | Intentionally not done; outside T-011 scope and currently prohibited by policy decision                                                          |

**Final recommendation:** move T-011 to `Review`. Open a source-permission
action with SkyNomad before T-013 treats Leonardo records as ML data. In
parallel, manually validate the known flight pages and source takeoff IDs using
the checklist above. If SkyNomad provides an approved export, use that instead
of scraping.

## 17. Primary references

- [SkyNomad home](https://www.skynomad.com/)
- [SkyNomad news archive](https://www.skynomad.com/skynomad_news.htm)
- [SkyNomad sitemap index](https://www.skynomad.com/sitemap_index.xml)
- [SkyNomad main-site robots.txt](https://www.skynomad.com/robots.txt)
- [SkyNomad forum/Leonardo robots.txt](https://forum.skynomad.net/robots.txt)
- [SkyNomad paragliding links](https://www.skynomad.com/bg/%D0%B2%D1%80%D1%8A%D0%B7%D0%BA%D0%B8-%D0%B7%D0%B0-%D0%BF%D0%B0%D1%80%D0%B0%D0%BF%D0%BB%D0%B0%D0%BD%D0%B5%D1%80%D0%B8%D0%B7%D1%8A%D0%BC)
- [SkyNomad August 2017 report](https://www.skynomad.com/news/august-2017)
- [SkyNomad September 2020 report](https://www.skynomad.com/news/september-2020)
- [SkyNomad contact](https://www.skynomad.com/contact)
- [WordPress REST Posts reference][wp-posts]
- [WordPress REST pagination reference][wp-pagination]
- [Leonardo XC Server source][leo-repo]
- [Cloudflare Content Signals policy][cloudflare-content-signals]
- [Cloudflare `use` signal announcement][cloudflare-use-signal]

### Leonardo source snapshot used

Repository commit inspected:
`865ab1640e33b4cbaab6948675559ba832e3dd75` (2024-07-11).
Commit-pinned links are used so later source changes do not silently change the
evidence:

- [SkyNomad installation reference][leo-install]
- [flight-list columns and selectors][leo-list]
- [advanced filter UI][leo-filter-ui]
- [filter field encoding][leo-filter-logic]
- [route/category and distance semantics][leo-filter-distance]
- [internal flight endpoints][leo-ext-flight]
- [SEO/rewrite routes][leo-routes]
- [IGC authorization/captcha flow][leo-igc]

[wp-posts]: https://developer.wordpress.org/rest-api/reference/posts/
[wp-pagination]: https://developer.wordpress.org/rest-api/using-the-rest-api/pagination/
[cloudflare-content-signals]: https://blog.cloudflare.com/content-signals-policy/
[cloudflare-use-signal]: https://blog.cloudflare.com/content-independence-day-ai-options/
[leo-repo]: https://github.com/leonardoxc/leonardoxc
[leo-license]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_EXT_download_igc.php#L1-L10
[leo-install]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_program_info.php#L41-L44
[leo-list]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_list_flights.php#L561-L724
[leo-filter-ui]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_filter.php#L296-L557
[leo-filter-logic]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/CL_filter.php#L108-L136
[leo-filter-distance]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/CL_filter.php#L775-L813
[leo-ext-flight]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/EXT_flight.php#L424-L634
[leo-routes]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_conf_htaccess.php#L62-L96
[leo-igc]: https://github.com/leonardoxc/leonardoxc/blob/865ab1640e33b4cbaab6948675559ba832e3dd75/GUI_EXT_download_igc.php#L36-L116
