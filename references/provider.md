# Official sources and observed semantics

Verified 2026-09-11. These are public read-only search surfaces, not a supported API contract.

- Discovery: https://recreation.parks.lacity.gov/discover-facilities
- Pay court directory: https://recreation.parks.lacity.gov/sports/tennis/pay
- Other court permits/contact route: https://recreation.parks.lacity.gov/reservations/facility-permits
- WebTrac search: https://reg.recreation.parks.lacity.gov/web/wbwsc/webtrac.wsc/search.html

## Required search parameters

`InterfaceParameter=Iframe_Live_WebTrac`, `arwebsearch_buttonsearch=yes`, `module=FR`, `date=MM/DD/YYYY`, `begintime=8:00 AM` (or requested start), and `location` from a verified official search link. Omitting the interface/location can redirect to facility discovery instead of returning courts. Never treat that redirect as an empty calendar.

Verified location values: `VNSO Pay Tennis`, `Vermont Canyon Pay Tennis`, `Westchester Pay Tennis`. Other locations must be obtained from official booking links before adding them; compact new-site tokens such as `BalboaPayTennis` are not automatically equivalent to legacy WebTrac values.

## Read-only extraction

The table selector is `table#frwebsearch_output_table` (the provider repeats IDs). Each row has `td[data-title]` for Facility Description, Location Description, Class Description, and Price. `.dateblock[data-tooltip]` provides the full date. Item details use `iteminfo.html?Module=FR&FMID=...`.

Read per-court rules from `.result-header__info` whose `h2` matches the court name. Read time blocks from `a.cart-button--state-block`:

- `success` class and `data-tooltip="Book Now"`: available.
- `error` class and tooltip containing `Unavailable`: unavailable.
- Anything else: unknown.

The search page contains action URLs and CSRF tokens. The bundled extractor emits only status markup and sanitized detail links; never export or follow action URLs. Booking links must be search/detail links, not `action=UpdateSelection` links.

Calendar URLs and visible dates must match the requested date. Snapshot fixtures are historical test evidence, never current availability. Inspect result count/pagination before claiming an exhaustive location/day search.

## Current limitations

Direct HTTP requests returned 403 in this environment; the browser successfully displayed dated calendars. The standalone script therefore emits actionable browser fallback requests. The new `discover-activities?reserve=true` page did not render a calendar during inspection. The old WebTrac interface worked with the full parameters above.

Non-calendar sports use official facility discovery and staff-contact guidance. Seed records do not establish that every court at a site is public, reservable, or currently operating. Confirm them on the source page at lookup time.
