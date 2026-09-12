# LA City Facility Availability Skill

This skill checks covered Los Angeles City facility availability for supported courts, rentals, and schedules.

## Install (local skill layouts)

- **Codex**: place this directory at your configured skill root and reference `find-la-city-courts-availability`.
- **Other agent runtimes**: use the host/runtime's local skill loading flow.

## Use

Run `scripts/find_availability.py` through the skill runner or call it directly in diagnostics:

```bash
python3 find-la-city-courts-availability/scripts/find_availability.py "VNSO" \
  --date YYYY-MM-DD \
  [--start HH:MM --end HH:MM] \
  [--sport tennis|pickleball|paddle tennis|basketball|racquetball]
```

Use the skill prompt when running in-agent; the command examples are for local verification only.

## Supported facilities

The coverage list is authoritative in:

- [references/covered-facilities.md](references/covered-facilities.md)

For unsupported facilities, return the official directory link from:

- [https://recreation.parks.lacity.gov/discover-facilities](https://recreation.parks.lacity.gov/discover-facilities)

## Testing notes

- Unit + fixture checks:

```bash
python3 -m unittest discover -s tests -q
```

- Live browser checks:

```bash
python3 tests/check_live_calendars.py --date YYYY-MM-DD
```

