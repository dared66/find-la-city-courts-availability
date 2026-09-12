---
name: find-la-city-courts-availability
description: LA City courts, Westwood racquetball, Travel Town rentals and Cheviot Hills schedules. Check the explicit coverage list and live availability; politely decline unsupported facilities with an official website link.
---

# LA City facility availability

The supported scope is the explicit list in [covered-facilities.md](references/covered-facilities.md). Read it before selecting a route. It supersedes the older seed catalog and audit notes. Do not expand coverage during a user lookup.

## Scope and unsupported requests

Match both the facility and requested resource type. A covered park does not mean every amenity there is covered. For example, Westwood racquetball is covered but Westwood gym availability is not; Riverside tennis is covered but Griffith Park pickleball is not.

For a request outside the list, respond briefly and politely:

> Sorry, this skill doesn’t support availability checks for [facility/resource] yet. You can check [official facility website].

Use a known official facility URL, or perform one focused search solely to locate that URL. If no facility URL can be verified, link the [LA City facility directory](https://recreation.parks.lacity.gov/discover-facilities). Do not invent a URL, recommend an arrival time, substitute drop-in advice, or continue investigating availability. Do not say the facility itself is unavailable or cannot be reserved.

For mixed requests, check the covered resources and label unsupported ones separately. For citywide or area searches, search the matching covered facilities only and explicitly say coverage is limited to this list. Omitted sport/resource means all covered types in the requested area. Do not imply a comprehensive citywide inventory.

## Calendar lookups

Resolve the date and optional time window in America/Los_Angeles. Ask for the date if missing. A start without an end means one hour; no time means any time on that date. Use the exact reservation route in the coverage reference and verify the displayed date and all row dates.

For all eleven WebTrac location routes in the coverage reference (eight pay-court locations, Westwood racquetball, Travel Town and Palisades), use the installed live helper first.

```bash
python3 "<skill>/scripts/live_calendar.py" --location "<exact location token from coverage reference>" --date YYYY-MM-DD [--start HH:MM --end HH:MM] [--sport pickleball]
```

Run the command to completion and read its JSON. `retrieval: live_isolated_chrome` with `ok: true` confirms a fresh retrieval. It launches and closes an isolated normal Chrome window with a temporary profile. It does not depend on the host browser session, a Chrome debugging session, personal browser cookies, or direct HTTP. Do not replace it with the old HTTP helper when direct requests are blocked.

The helper reads every resource page and queries time starts every two hours for long windows. Court results are normalized; Travel Town and Palisades retain raw block classes/tooltips for the availability interpretation below. Do not use `--sport` for those two calendars. A zero sport-match count means no matching resource configuration was returned, not all courts booked. Preserve the observation timestamp in the answer.

For Cheviot Hills schedule sheets, use the public spreadsheet links in the coverage reference. This helper covers WebTrac only.

Read every result page: Balboa currently has 22 entries over two pages. Also check time-block clipping; the portal can limit the number of displayed blocks. A midnight query alone does not prove full-day coverage. If remaining time ranges cannot be read through the public controls, disclose incomplete time coverage.

## Availability meaning

- `success` plus `Book Now`: online-bookable provider time block. No reservation has been made.
- `success` plus `Inquiry Only`: inquiry-only provider time block; staff confirmation/booking required. Do not count it as online-bookable.
- `error` plus `Unavailable`: provider-reported unavailability or restriction; preserve the explanatory tooltip. Advance-booking or Pro-court restrictions do not prove occupancy.
- Missing slots, empty results, redirects or errors: availability not verified. Never infer all courts are booked.

A requested interval must be continuously available on the same resource. Keep booking-duration limits and exact slot boundaries separate from open time. Court names override generic class labels; the provider's `Pickelball` spelling means pickleball. Shared tennis/pickleball configurations overlap and cannot be counted as independent courts. Inspect Pro-court rules separately.

For Cheviot Hills spreadsheets, use the linked calendar for the requested date, then read its rental rules. Report published bookings/closures or “no booking shown”; an empty cell is not confirmed availability. Requests still need staff approval and the stated lead time. The field sheet includes basketball schedule rows, but its rental rules exclude basketball rentals; do not offer those as reservable.

## Retrieval failures and answer

If a covered lookup fails, say:

> Sorry, I couldn’t check live availability for [facility/resource] right now. You can check [official facility/reservation website].

State a brief concrete reason if useful. One transient retry is enough. If the live helper fails, stop rather than switching to the broken browser_exec route, installing packages, changing browser settings or attempting stealth workarounds. Never replay a stored snapshot as a live result.

For successful lookups, lead with facility/resource, date/window and the observed result. Keep online-bookable, inquiry-only and published-schedule results distinct. Include source links, observation time and relevant restrictions. Never replace a failed or unsupported lookup with generic recommendations. Never select booking slots, create a cart, sign in to book, pay, submit permit forms or contact staff as part of this skill.

Render every online-bookable slot with a clickable **Book Now** label using that block's `booking_url`: `5–6 PM — [Book Now](booking_url)`. The link opens the official facility calendar on the slot's date and start time; the user selects the court and slot there. Court-detail links may be additional context but do not replace Book Now links. Do not use session-specific action URLs, CSRF tokens, or cart links. Inquiry-only, unavailable and unknown slots must not be labeled Book Now.
