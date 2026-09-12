# Validation notes

## Verification status

The live helper and parser were validated against public LA City pages with the commands below. Run these before each release:

### 1) Unit checks

```bash
python3 -m unittest discover -s tests -q
```

### 2) Live browser checks

```bash
python3 tests/check_live_calendars.py --date YYYY-MM-DD
```

Optional filters:

- `--location` to target one supported route.
- `--start` and `--end` to check a specific time window.

`check_live_calendars.py` runs through `scripts/live_calendar.py`, so failures here usually indicate provider rendering or selector changes.

## Expected live retrieval surface

The helper currently supports locations listed in `references/covered-facilities.md` and checks every available result page. Keep this list up to date with provider naming or coverage changes.

## Notes

- This skill reads only public pages and does not perform bookings.
- Empty or unknown cells in non-WebTrac schedules are not treated as confirmed availability.
- If direct HTTP routes fail for a location, keep the `snapshot` fallback path for diagnostics instead of changing provider method logic silently.
