"""XCContest rendered-DOM selectors shared by collection and offline parsing."""

FLIGHTS_CONTAINER_SELECTOR = "#flights"
SEASON_SELECTOR = 'div.under-bar select[onchange*="document.location.replace"]'
COUNTRY_SELECTOR = 'select[name="filter[country]"]'
GLIDER_SELECTOR = 'select[name="filter[detail_glider_catg]"]'
DATE_SELECTOR = 'select[name="filter[date]"]'
ROW_SELECTOR = f"{FLIGHTS_CONTAINER_SELECTOR} table.XClist tbody tr[id^='flight-']"
SORT_SELECTOR_TEMPLATE = (
    f"{FLIGHTS_CONTAINER_SELECTOR} table.XClist thead a[href*='flights[sort]={{sort_key}}']"
)

TAKEOFF_CELL_SELECTOR = "td:nth-child(2)"
DISTANCE_SELECTOR = "td.km strong"
LAUNCH_LINK_SELECTOR = "a.lau"
LAUNCH_COUNTRY_SELECTOR = ".cic"
ROUTE_SELECTOR = "div.disc-vp[title]"
DURATION_SELECTOR = "td.dur strong"
DETAIL_LINK_SELECTOR = "a.detail"
