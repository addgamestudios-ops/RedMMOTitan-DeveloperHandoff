# Fab Watch

A tiny helper that watches [Fab](https://www.fab.com) (Epic's asset marketplace) for
**Limited-Time Free** and **on-sale** packs, so you don't miss free/discounted assets for the game.

It uses **Browserbase Fetch** — a no-browser page-content API — so it:
- **can't get bot-blocked** (no automated browser fingerprint to detect), and
- **costs no LLM tokens** (no Model Gateway usage, so it never touches the Free plan's $5 token cap).

That makes it reliable on the Browserbase **Free plan**. (Fetch has a limited monthly call allowance on
Free; each run makes 2 calls.)

## Setup (once)

You need the `browse` CLI (`npm install -g browse@latest`) and your Browserbase API key in the env.
**Don't hardcode the key in this folder** — set it in your shell:

```bash
export BROWSERBASE_API_KEY=bb_live_xxx
```

## Run

```bash
python3 fab_watch.py
```

Prints the current free + on-sale lists and writes **`fab_free.json`** next to the script:

```json
{
  "fetched_at": "2026-07-07T17:03:...Z",
  "free_until": "July 14 at 9:59 AM ET",
  "limited_time_free": [
    { "title": "Science Fiction Desert City Kit", "seller": "LAYA DESIGN",
      "url": "https://www.fab.com/listings/...", "free_until": "July 14 at 9:59 AM ET" }
  ],
  "on_sale_sample": [ { "title": "Modular Sci-Fi Base - Indoor", "url": "https://www.fab.com/listings/..." } ]
}
```

Your UE tools can read `fab_free.json` directly (e.g. surface new free packs in an editor panel).

## Optional upgrades

- **Run it on a schedule.** Add a `cron` entry on your Mac, or deploy it to run in Browserbase's cloud
  on a schedule/webhook with [Functions](https://docs.browserbase.com/platform/runtime/overview)
  (Functions are TypeScript — the logic ports directly).
- **Full on-sale coverage / filters (by category, discount %, engine).** The `/search` results beyond the
  first page are JS-paginated; for deep coverage switch that fetch to a
  [Stagehand](https://docs.browserbase.com/welcome/quickstarts/stagehand) browser session with
  `extract()`. (Uses a cloud browser + Model Gateway tokens — counts against the Free plan's $5 cap.)
- **Your own Library / wishlist / "already owned" checks.** Those pages need your Epic login, which means
  a real browser session plus [Contexts](https://docs.browserbase.com/platform/browser/core-features/contexts)
  to persist the sign-in across runs.
- **If Fab ever starts blocking Fetch,** escalate to a Verified + proxied browser session (a paid
  Browserbase feature) — not needed today (Fab returns a clean `200` to Fetch).
