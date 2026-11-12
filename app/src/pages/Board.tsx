import { useMemo, useState } from 'react'
import type { Board as BoardData, Game, LensKey } from '../data/types'
import { bucketOrder, etBucket, longDate, etStamp } from '../data/time'
import { GameCard } from '../components/GameCard'
import { CompactRow } from '../components/CompactRow'
import { Drawer } from '../components/Drawer'

const WORDS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen']

export function matchesTeam(g: Game, term: string): boolean {
  if (!term) return true
  const hay = `${g.away.abbr} ${g.away.city} ${g.away.name} ${g.home.abbr} ${g.home.city} ${g.home.name}`.toLowerCase()
  return hay.includes(term)
}

interface Props {
  board: BoardData
  snapshotControls?: React.ReactNode
  onLineups?: (id: string) => void
  onProps?: (t: { players: number[]; stat?: 'g' | 'a' | 'p' | 'sog'; line?: number }) => void
}

export function Board({ board, snapshotControls, onLineups, onProps }: Props) {
  const [time, setTime] = useState<string>('all')
  const [view, setView] = useState<'cards' | 'list'>('cards')
  const [term, setTerm] = useState('')
  const [smashOnly, setSmashOnly] = useState(false)
  const [slots, setSlots] = useState<LensKey[]>(board.default_slots)
  const [open, setOpen] = useState<string | null>(null)

  const games = board.games
  const buckets = useMemo(() => {
    const seen = new Map<string, number>()
    for (const g of games) seen.set(etBucket(g.start_utc), bucketOrder(g.start_utc))
    return [...seen.entries()].sort((a, b) => a[1] - b[1]).map(([k]) => k)
  }, [games])
  const activeTime = buckets.includes(time) ? time : 'all'

  const shown = useMemo(
    () =>
      games
        .filter((g) => (activeTime === 'all' || etBucket(g.start_utc) === activeTime) && matchesTeam(g, term.trim().toLowerCase()) && (!smashOnly || g.smash?.flag))
        .sort((a, b) => bucketOrder(a.start_utc) - bucketOrder(b.start_utc) || a.id.localeCompare(b.id)),
    [games, activeTime, term, smashOnly],
  )
  const ideas = games.reduce((n, g) => n + slots.filter((l) => g.lenses[l]?.length).length, 0)
  const smashCount = games.filter((g) => g.smash?.flag).length
  const pending = games.filter((g) => g.smash?.flag === null && g.smash.label === 'IN PROCESS').length
  const openGame = open ? games.find((g) => g.id === open) ?? null : null
  const lensKeys = Object.keys(board.lenses) as LensKey[]

  return (
    <>
      <section className="hero">
        <div>
          <div className="eyebrow">
            NHL <span style={{ color: '#426e7b' }}>/</span> DAILY SLATE · {longDate(board.date).toUpperCase()}
          </div>
          <h1>
            Tonight's <span>board.</span>
          </h1>
          <p>
            Every matchup. Your bets. Three equally visible angles per game — pick which three.
            {board.snapshot_label ? ` ${board.snapshot_label}.` : ''}
          </p>
        </div>
        <div className="demo-switch" role="group" aria-label="Choose play lenses">
          {slots.map((lens, i) => (
            <label key={i} className="slot-select">
              <span className="slot-num">0{i + 1}</span>
              <select
                aria-label={`Play slot ${i + 1}`}
                value={lens}
                onChange={(e) => setSlots(slots.map((s, j) => (j === i ? (e.target.value as LensKey) : s)))}
              >
                {lensKeys.map((k) => (
                  <option key={k} value={k}>
                    {board.lenses[k]}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {snapshotControls}
        </div>
      </section>

      <section className="summary">
        <div className="stat">
          <div className="stat-label">Games on slate</div>
          <div className="stat-main">
            <span className="stat-value" data-testid="game-count">
              {String(games.length).padStart(2, '0')}
            </span>
            <span className="stat-suffix">of 16 max</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">Start-time windows</div>
          <div className="stat-main">
            <span className="stat-value">{String(buckets.length).padStart(2, '0')}</span>
            <span className="stat-suffix">Eastern Time</span>
          </div>
        </div>
        <div className={`stat${smashCount ? ' smash-stat' : ''}`} role="button" tabIndex={0} title="Smash games: total ≥ 6.5 with the over juiced. Click to filter." onClick={() => setSmashOnly(!smashOnly)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setSmashOnly(!smashOnly)} style={{ cursor: 'pointer' }}>
          <div className="stat-label">Smash games{smashOnly ? ' · filtered' : ''}</div>
          <div className="stat-main">
            <span className="stat-value">{String(smashCount).padStart(2, '0')}</span>
            <span className="stat-suffix">{pending ? `${pending} in process` : 'O/U ≥ 6.5, over juiced'}</span>
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">Verified plays</div>
          <div className="stat-main">
            <span className="stat-value">{String(ideas).padStart(2, '0')}</span>
            <span className="stat-suffix">of {games.length * 3} slots</span>
          </div>
        </div>
        <div className="stat focus-stat">
          <div className="stat-label">WORKSPACE / EQUAL-WEIGHT PLAYS</div>
          <strong>
            One slate. {WORDS[games.length] ?? games.length} decisions.
          </strong>
          <small>
            Model run {etStamp(board.generated_utc)} ET · lenses: {slots.map((s) => board.lenses[s]).join(' / ')}
          </small>
        </div>
      </section>

      <section aria-label="NHL matchups">
        <div className="boardbar">
          <div className="board-heading">
            <h2>Game slate</h2>
            <span className="count" data-testid="matchup-count">
              {shown.length} MATCHUP{shown.length === 1 ? '' : 'S'}
            </span>
          </div>
          <div className="toolbar">
            <div className="time-filter" role="group" aria-label="Filter by puck-drop time">
              <button className={activeTime === 'all' ? 'active' : ''} aria-pressed={activeTime === 'all'} onClick={() => setTime('all')}>
                All <span>{games.length}</span>
              </button>
              {buckets.map((b) => (
                <button key={b} className={activeTime === b ? 'active' : ''} aria-pressed={activeTime === b} onClick={() => setTime(b)}>
                  {b}
                </button>
              ))}
            </div>
            <label className="search" title="Filter by team">
              <svg viewBox="0 0 24 24">
                <circle cx="10.5" cy="10.5" r="7" />
                <path d="m16 16 5 5" />
              </svg>
              <input type="search" aria-label="Search teams" placeholder="Find a team" value={term} onChange={(e) => setTerm(e.target.value)} />
            </label>
            <div className="views" role="group" aria-label="Layout view">
              <button className={view === 'cards' ? 'selected' : ''} aria-pressed={view === 'cards'} title="Card layout" onClick={() => setView('cards')}>
                <svg viewBox="0 0 24 24">
                  <rect x="2" y="3" width="9" height="8" rx="1" />
                  <rect x="13" y="3" width="9" height="8" rx="1" />
                  <rect x="2" y="13" width="9" height="8" rx="1" />
                  <rect x="13" y="13" width="9" height="8" rx="1" />
                </svg>{' '}
                Cards
              </button>
              <button className={view === 'list' ? 'selected' : ''} aria-pressed={view === 'list'} title="Compact list layout" onClick={() => setView('list')}>
                <svg viewBox="0 0 24 24">
                  <path d="M8 5h13M8 12h13M8 19h13" />
                  <path d="M3 5h1M3 12h1M3 19h1" />
                </svg>{' '}
                List
              </button>
            </div>
          </div>
        </div>
        <div className="board-notes">
          <span>{activeTime === 'all' ? 'ALL PUCK DROPS · EASTERN TIME' : `${activeTime} PUCK DROP · EASTERN TIME`}</span>
          <span className="rule" />
          <span className="muted">MONEYLINE / GAME TOTAL / THREE FULL BETTING ANGLES</span>
        </div>
        <div aria-live="polite">
          {games.length === 0 ? (
            <div className="state-box">No NHL games on {longDate(board.date)}. The board fills in the morning of the next slate.</div>
          ) : shown.length === 0 ? (
            <div className="empty">No games match the selected time and team search. Try All or clear your search.</div>
          ) : view === 'cards' ? (
            <div className="game-grid">
              {shown.map((g) => (
                <GameCard key={g.id} game={g} slots={slots} lensLabels={board.lenses} onOpen={setOpen} onProps={onProps} />
              ))}
            </div>
          ) : (
            <div className="compact-wrap">
              <div className="compact-head">
                <span>PUCK DROP</span>
                <span>MATCHUP / RECORDS</span>
                <span>AWAY / HOME ML</span>
                <span>O/U</span>
                <span>TOP PLAY 01 + RATIONALE</span>
                <span>TOP PLAY 02 + RATIONALE</span>
                <span>TOP PLAY 03 + RATIONALE</span>
                <span>DETAIL</span>
              </div>
              {shown.map((g) => (
                <CompactRow key={g.id} game={g} slots={slots} lensLabels={board.lenses} onOpen={setOpen} />
              ))}
            </div>
          )}
        </div>
      </section>

      <footer className="legend">
        <span>
          <strong>Our prices, not a book's.</strong> Every number is the model's fair price from this season's boxscores and
          Daily Faceoff lineups; "need" is the worst price worth taking. Moneylines from {board.sources.moneyline}. Game totals
          unavailable until the odds feed lands. Not betting advice.
        </span>
        <span className="version">ICEBOARD / {board.mode === 'live' ? 'LIVE' : 'SNAPSHOT'} · {board.date}</span>
      </footer>

      <Drawer game={openGame} lensLabels={board.lenses} onClose={() => setOpen(null)} onLineups={onLineups} onProps={onProps} />
    </>
  )
}
