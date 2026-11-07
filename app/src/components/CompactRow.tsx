import type { Game, LensKey, Play } from '../data/types'
import { etTime } from '../data/time'
import { Crest, playFor } from './GameCard'

function CompactPlay({ play, i, lensLabel }: { play: Play | null; i: number; lensLabel: string }) {
  return (
    <div className={`compact-play${i === 0 ? ' first' : ''}`}>
      <span className="tiny">
        PLAY 0{i + 1} · {lensLabel.toUpperCase()}
      </span>
      {play ? (
        <>
          <div className="headline">
            <b>{play.selection}</b>
            <em>{play.fair}</em>
          </div>
          <p>{play.rationale}</p>
        </>
      ) : (
        <>
          <div className="headline">
            <b style={{ color: '#7f98a8' }}>No verified play yet</b>
          </div>
          <p>Nothing clears the bar.</p>
        </>
      )}
    </div>
  )
}

interface Props {
  game: Game
  slots: LensKey[]
  lensLabels: Record<LensKey, string>
  onOpen: (id: string) => void
}

export function CompactRow({ game, slots, lensLabels, onOpen }: Props) {
  const { away, home, markets } = game
  return (
    <article className="compact-row">
      <div className="compact-clock">{etTime(game.start_utc)} ET</div>
      <div className="compact-match">
        <Crest team={away} small />
        <Crest team={home} small />
        <div className="compact-teams-label">
          <b>
            {away.abbr} @ {home.abbr}
          </b>
          <small>
            {away.record} / {home.record}
          </small>
        </div>
      </div>
      <div className="compact-market">
        <b>
          {markets.moneyline.away ?? '—'} <span style={{ color: '#698b9e' }}>/</span>{' '}
          <span style={{ color: '#93dedb' }}>{markets.moneyline.home ?? '—'}</span>
        </b>
        <small>
          {away.abbr} away / {home.abbr} home
        </small>
      </div>
      <div className="compact-total" style={markets.total.line == null ? { fontSize: 10, color: '#6f8fa3' } : undefined}>
        {markets.total.line ?? 'N/A'}
      </div>
      {slots.map((lens, i) => (
        <CompactPlay key={lens + i} play={playFor(game, lens)} i={i} lensLabel={lensLabels[lens]} />
      ))}
      <button className="go" onClick={() => onOpen(game.id)} title="Open full breakdown" aria-label={`Open ${away.abbr} at ${home.abbr} breakdown`}>
        ↗
      </button>
    </article>
  )
}
