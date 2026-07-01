# A7-CGG jet tracker — auto-updating data feed

This repo pulls raw ADS-B history for tail **A7-CGG** (ICAO `06a1cc`) once a day and
publishes it as a browser-readable JSON, so the tracker webpage can refresh its
**completed-leg history** on its own — no manual rebuild.

## What's here
- `collect.py` — pulls adsb.lol globe-history traces (Jun 9 → today), segments them
  into flight legs, geocodes each endpoint to the nearest airport, writes
  `data/a7cgg.json`. Standard library only.
- `.github/workflows/update.yml` — runs `collect.py` daily and commits the JSON.
- `data/a7cgg.json` — the output the webpage reads.

## One-time setup (~5 min)
1. Create a new GitHub repo (public is simplest) and add these three files.
2. **Settings → Actions → General → Workflow permissions →** select
   **"Read and write permissions"**, save. (Lets the daily job commit.)
3. Go to the **Actions** tab, pick **update-a7cgg**, click **Run workflow** once to
   seed `data/a7cgg.json`. After that it runs automatically every day at 08:00 UTC.
4. Your feed URL is:
   ```
   https://raw.githubusercontent.com/<YOUR-USER>/<YOUR-REPO>/main/data/a7cgg.json
   ```
   That URL is served with `access-control-allow-origin: *`, so the webpage can fetch it.

## Wire it to the webpage
Open the tracker HTML, find this line near the top of the script:
```js
const REMOTE_URL = "";   // paste your raw GitHub JSON URL here
```
Paste your feed URL between the quotes and save. Done — on load and on **↻ Refresh**
the page pulls the latest legs from the feed and falls back to the built-in snapshot
if the feed is ever unreachable.

## Notes
- Change the schedule by editing the `cron:` line (it's UTC).
- `collect.py` always rebuilds the full history, so a run is self-correcting.
- Nothing here needs an API key; adsb.lol and OurAirports are both free/keyless.
