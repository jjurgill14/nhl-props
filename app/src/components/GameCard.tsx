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
      <img alt={`${team.city} ${team.name} logo`} loading="lazy" src={LOGO(team.abbr)} />
    </div>
  )
}

function BigTeam({ team, opp, position, xg, xgTone }: { team: TeamSide; opp: TeamSide; position: 'AWAY' | 'HOME'; xg: number | null; xgTone: string }) {
  const st = team.goalie_status
  const cls = st === 'Confirmed' ? 'ok' : st === 'Likely' || st === 'Expected' ? 'likely' : ''
  return (
    <div className="team">
      <Crest team={team} />
      <div className="team-name" title={`${team.city} ${team.name}`}>
        {team.city}
      </div>
      <div className="team-record">
        {team.record}
        {xg != null && (
          <span className={`xg ${xgTone}`} title="Market-implied expected goals tonight (vig removed; total split by the moneyline)">
            xG {xg.toFixed(2)}
          </span>
        )}
      </div>
      <div className="location">
        {position}
        {team.b2b && <span className="status-badge b2b">B2B</span>}
      </div>
      <div className="goalie-line" title={team.goalie_news ?? undefined}>
        🥅 <b>{team.goalie ?? 'TBD'}</b> <span className={cls}>{st ?? 'unconfirmed'}</span>
      </div>
      <RankStrip r={team.rates} opp={opp.rates} compact />
    </div>
  )
}

function amer(v: number | null | undefined): string {
  return v == null ? '—' : v > 0 ? `+${v}` : String(v)
}


export function TotalsBar({ game }: { game: Game }) {
  const { markets, away, home } = game
  const t = markets.total
  const line = t.line
  const m = game.market
  // one number drives everything: the market-implied total (vig removed) — green ≥ 6.35, amber ≥ 6.2, red below
  const lineTone = m?.tone ?? ''
  const juiceTone = lineTone
  const bml = markets.book_moneyline
  return (
    <div className="totals" title={game.smash?.why}>
      <div className="tot-main">
        <div className="tot-label">GAME O/U</div>
        {line != null ? (
          <div className={`tot-line ${lineTone}`} title={`Line ${line} · implied total ${m?.implied_total ?? '–'} after removing vig`}>
            {line}
            {m?.implied_total != null && <small>→ {m.implied_total.toFixed(2)}</small>}
          </div>
        ) : (
          <div className="tot-line none">{t.status === 'in process' ? 'LINE PENDING' : 'NO LINE'}</div>
        )}
      </div>
      <div className="tot-odds">
        {t.over != null ? (
          <>
            <div className={`tot-side ${juiceTone}`}>
              <span className="mark">{juiceTone === 'good' ? '✓' : juiceTone === 'bad' ? '✗' : '~'}</span>
              <span>OVER <b>{amer(t.over)}</b></span>
              {m?.fair_over && <small className="fair">fair {m.fair_over}</small>}
            </div>
            <div className="tot-side muted">
              <span className="mark"> </span>
              <span>UNDER <b>{amer(t.under)}</b></span>
            </div>
          </>
        ) : (
          <div className="tot-side muted">{t.status === 'in process' ? 'line pending' : 'no odds feed'}</div>
        )}
      </div>
      <div className="tot-ml">
        <span>{away.abbr} <b>{amer(bml?.away ?? (markets.moneyline.away ? Number(markets.moneyline.away) : null))}</b></span>
        <span>{home.abbr} <b>{amer(bml?.home ?? (markets.moneyline.home ? Number(markets.moneyline.home) : null))}</b></span>
      </div>
    </div>
  )
}

/** NHL schedule state -> card label. FUT/PRE upcoming · LIVE/CRIT in process · OFF/FINAL final */
export function gameState(status: string | null): { label: string; cls: string } {
  switch (status) {
    case 'LIVE':
    case 'CRIT':
      return { label: 'IN PROCESS', cls: 'live' }
    case 'OFF':
    case 'FINAL':
      return { label: 'FINAL', cls: 'final' }
    default:
      return { label: 'UPCOMING', cls: 'upcoming' }
  }
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
      className={`card${game.smash?.flag ? ' smash-card' : ''}`}
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
        <span className={`gstate ${gameState(game.status).cls}`}>{gameState(game.status).label}</span>
        <span className="head-center">
          {game.smash?.flag && <span className="status-badge smash" title={game.smash.why}>SMASH</span>}
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
        <BigTeam team={away} opp={home} position="AWAY" xg={game.market?.xg_away ?? null} xgTone={game.market?.xg_tone_away ?? ''} />
        <span className="vs">AT</span>
        <BigTeam team={home} opp={away} position="HOME" xg={game.market?.xg_home ?? null} xgTone={game.market?.xg_tone_home ?? ''} />
      </div>
      <TotalsBar game={game} />
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
