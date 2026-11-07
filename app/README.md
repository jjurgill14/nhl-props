# ICEBOARD — the app

React + TypeScript + Vite front end for `nhl-props`. It reads JSON the Python pipeline writes to `docs/`
(`board.json`, `boards/<date>.json`, `assets/`) and is built into `docs/app/` so GitHub Pages serves it at
https://jjurgill14.github.io/nhl-props/app/ — no server, no client-side secrets.

## Run locally
```
cd app && npm install
npm run dev        # http://localhost:5173/nhl-props/app/  (data proxied from ../docs; run the pipeline or `git pull` for fresh JSON)
npm test           # vitest: time filter (ET/DST), search, cards/list, drawer, lens slots, snapshot-vs-live
npm run build      # -> ../docs/app  (Actions does this after every pipeline job)
```

## Structure
- `src/data/types.ts` — the board contract (mirror of `src/nhl_props/board.py`)
- `src/data/time.ts` — all puck-drop display/filtering in America/New_York
- `src/components/` — Shell (rail + top bar), GameCard, CompactRow, Drawer: one per locked design element
- `src/pages/Board.tsx` — The Board; `Placeholder.tsx` — routes whose designs haven't been approved yet
- `src/board.css` — prototype CSS ported verbatim; additions are isolated at the bottom

## Modes
- **live** — `board.json`, written by the pipeline each morning and refreshed every 15 min pre-game.
- **snapshot** — `boards/<date>.json`, a real past slate; always labeled "not tonight". There is no invented data anywhere.
