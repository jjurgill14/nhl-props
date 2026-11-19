# Preview tooling (used from a Claude session, not by Actions)

`python3 tools/preview/standalone.py docs/board.json /tmp/ICEBOARD_<date>.html`
builds a single self-contained HTML of the app with the board, all player logs, logos,
badges and the jersey font embedded (what JJ opens on his phone/laptop when the Pages
site isn't reachable from the session). Needs `cd app && npm ci` first.

`python3 tools/preview/shot.py out.png /abs/path/to/preview.html` screenshots the
Lines & Lineups page headlessly (playwright + /usr/bin/google-chrome) for visual checks.

During game hours never dispatch the evening workflow — the loop holds the concurrency
lock. Rebuild locally instead: `PYTHONPATH=src python3 -c "from nhl_props import board; board.build('<date>')"`
then commit docs/ and push (`git pull --rebase -X theirs` on conflict, rebuild, push).
