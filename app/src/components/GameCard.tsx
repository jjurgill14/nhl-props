import type { Game, LensKey, Play, StatKey, TeamSide } from '../data/types'

export type PropsOpener = (t: { players: number[]; stat?: StatKey; line?: number }) => void

/** What a play means in props-view terms: which players, which stat, which line. */
export function propsFor(play: Play, lens: LensKey): { players: number[]; stat?: StatKey; line?: number } | null {
  const ids = (play.players ?? []).filter((x): x is number => typeof x === 'number')
  if (!ids.length) return null
  if (lens === 'two') return { players: ids, stat: 'p', line: 1.5 }
  if (lens === 'btts2') return null
  return { players: ids, stat: 'p', line: 0.5 }
}
import { LOGO } from '../data/load'
import { etTime } from '../data/time'
import { RankStrip } from './RankStrip'

export function Crest({ team, small = false }: { team: TeamSide; small?: boolean }) {
  return (
    <div className={small ? 'small-logo' : 'crest'} style={{ ['--logo-color' as string]: team.color }}>
      <b className="abbr">{team.abbr}</b>
      <img alt={`${team.city} ${team.name} logo`} loading="lazy" src={LOGO(team.abbr)} />
    </div>
  )
}

function BigTeam({ team, position }: { team: TeamSide; position: 'AWAY' | 'HOME' }) {
  const st = team.goalie_status
  const cls = st === 'Confirmed' ? 'ok' : st === 'Likely' || st === 'Expected' ? 'likely' : ''
  return (
    <div className="team">
      <Crest team={team} />
      <div className="team-name" title={`${team.city} ${team.name}`}>
        {team.city}
      </div>
      <div className="team-record">{team.record}</div>
      <div className="location">
        {position}
        {team.b2b && <span className="status-badge b2b">B2B</span>}
      </div>
      <div className="goalie-line" title={team.goalie_news ?? undefined}>
        🥅 <b>{team.goalie ?? 'TBD'}</b> <span className={cls}>{st ?? 'unconfirmed'}</span>
      </div>
      <RankStrip r={team.rates} compact />
    </div>
  )
}

export function playFor(game: Game, lens: LensKey): Play | null {
  return game.lenses[lens]?.[0] ?? null
}

export function PlayRow({ play, rank, lensLabel, onClick }: { play: Play | null; rank: number; lensLabel: string; onClick?: () => void }) {
  if (!play) {
    return (
      <div className="play-row empty-play">
        <span className="rank">{rank}</span>
        <span className="bet">No verified play yet</span>
        <span className="bet-odds" style={{ opacity: 0.5 }}>
          —
        </span>
        <span className="reason">{lensLabel}: nothing clears the bar for this game.</span>
      </div>
    )
  }
  return (
    <div
      className={`play-row${onClick ? ' clickable' : ''}`}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={onClick ? 'Open player props' : undefined}
      onClick={(e) => {
        if (!onClick) return
        e.stopPropagation()
        onClick()
      }}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          e.stopPropagation()
          onClick()
        }
      }}
    >
      <span className="rank">{rank}</span>
      <span className="bet" title={play.selection}>
        {play.selection}
      </span>
      <span className="bet-odds" title={`fair ${play.fair} · need ${play.need} or better`}>
        {play.fair}
      </span>
      <span className="reason" title={play.rationale}>
        <span className="need">need {play.need} · </span>
        {play.rationale}
      </span>
    </div>
  )
}

interface Props {
  game: Game
  slots: LensKey[]
  lensLabels: Record<LensKey, string>
  onOpen: (id: string) => void
  onProps?: PropsOpener
}

export function GameCard({ game, slots, lensLabels, onOpen, onProps }: Props) {
  const { away, home, markets } = game
  const label = `Open ${away.abbr} at ${home.abbr} breakdown`
  return (
    <article
      className="card"
      role="button"
      tabIndex={0}
      aria-label={label}
      style={{ ['--team-accent' as string]: home.color }}
      onClick={(e) => {
        if (!(e.target as HTMLElement).closest('button, .play-row.clickable')) onOpen(game.id)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(game.id)
        }
      }}
    >
      <div className="card-head">
        <span className="game-num">
          MATCHUP / {game.id}
          {game.status === 'LIVE' && <span className="status-badge live">LIVE</span>}
          {(game.status === 'OFF' || game.status === 'FINAL') && <span className="status-badge final">FINAL</span>}
        </span>
        <span className="game-time">
          <svg viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 6v6l4 2" />
          </svg>
          {etTime(game.start_utc)} ET
        </span>
      </div>
      <div className="matchup">
        <BigTeam team={away} position="AWAY" />
        <span className="vs">AT</span>
        <BigTeam team={home} position="HOME" />
      </div>
      <div className="markets">
        <div className="market-cell">
          <div className="market-label">{away.abbr} ML</div>
          <div className="market-value">{markets.moneyline.away ?? '—'}</div>
          <div className="market-under">AWAY</div>
        </div>
        <div className="market-cell">
          <div className="market-label">GAME O/U</div>
          {markets.total.line != null ? (
            <div className="market-value total">{markets.total.line}</div>
          ) : (
            <div className="market-value unavailable">ODDS UNAVAILABLE</div>
          )}
          <div className="market-under">{markets.total.line != null ? 'GOALS' : 'NO FEED'}</div>
        </div>
        <div className="market-cell">
          <div className="market-label">{home.abbr} ML</div>
          <div className="market-value favored">{markets.moneyline.home ?? '—'}</div>
          <div className="market-under">HOME</div>
        </div>
      </div>
      <div className="play-section">
        <div className="play-head">
          <h3>
            TOP PLAYS <span>/ 03 EQUAL WEIGHT</span>
          </h3>
          <span className="tag">OUR FAIR PRICE</span>
        </div>
        <div className="play-stack">
          {slots.map((lens, i) => {
            const play = playFor(game, lens)
            const t = play && onProps ? propsFor(play, lens) : null
            return <PlayRow key={lens + i} play={play} rank={i + 1} lensLabel={lensLabels[lens]} onClick={t ? () => onProps!(t) : undefined} />
          })}
        </div>
      </div>
      <div className="card-foot">
        <span className="foot-note">{markets.moneyline.provider?.toUpperCase() ?? 'NO ODDS'} · LINEUP {home.lineup_stale ? 'STALE' : 'CURRENT'}</span>
        <button type="button" onClick={() => onOpen(game.id)}>
          OPEN BREAKDOWN ↗
        </button>
      </div>
    </article>
  )
}
