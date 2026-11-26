import type { SplitSel } from '../data/types'
import { VENUE_OPTS, WINDOW_OPTS } from '../data/splits'

/** Window / venue / defense-view toggles. One selection drives the rank strips and the leaders. */
export function SplitToggles({ sel, onChange, hasSplits = true }: { sel: SplitSel; onChange: (s: SplitSel) => void; hasSplits?: boolean }) {
  return (
    <div className="split-toggles" role="group" aria-label="Stat window, venue and defense view">
      <div className="seg" role="group" aria-label="Window">
        <span className="seg-lbl">WINDOW</span>
        {WINDOW_OPTS.map((o) => (
          <button key={o.key} type="button" disabled={!hasSplits && o.key !== 'season'} className={sel.window === o.key ? 'on' : ''} aria-pressed={sel.window === o.key} onClick={() => onChange({ ...sel, window: o.key })}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="seg" role="group" aria-label="Venue">
        <span className="seg-lbl">VENUE</span>
        {VENUE_OPTS.map((o) => (
          <button key={o.key} type="button" title={o.title} disabled={!hasSplits && o.key !== 'all'} className={sel.venue === o.key ? 'on' : ''} aria-pressed={sel.venue === o.key} onClick={() => onChange({ ...sel, venue: o.key })}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="seg" role="group" aria-label="Defense shown with each team">
        <span className="seg-lbl">DEFENSE SHOWN</span>
        <button type="button" title="Each team's offense next to the OPPONENT's defense — the matchup read" className={sel.defense === 'opp' ? 'on' : ''} aria-pressed={sel.defense === 'opp'} onClick={() => onChange({ ...sel, defense: 'opp' })}>
          Opponent's
        </button>
        <button type="button" title="Each team's offense next to its OWN defense" className={sel.defense === 'own' ? 'on' : ''} aria-pressed={sel.defense === 'own'} onClick={() => onChange({ ...sel, defense: 'own' })}>
          Own
        </button>
      </div>
    </div>
  )
}
