import type { Board, Game, LeaderBlock, RateBlock, SplitSel, StatKey, TeamSide } from '../data/types'
import { LOGO } from '../data/load'
import { etTime, longDate } from '../data/time'
import { cutLabel, leadersFor, ratesFor } from '../data/splits'
import { chipTone } from '../components/RankStrip'
import { SplitToggles } from '../components/SplitToggles'
import { PlayRow, TotalsBar, playFor, propsFor, type PropsOpener } from '../components/GameCard'

type RK = 'gf' | 'sf' | 'pp' | 'ga' | 'sa' | 'pk'
const OFF: { key: RK; label: string; title: string }[] = [
  { key: 'gf', label: 'GOALS / GM', title: 'Goals for per game (#1 = most)' },
  { key: 'sf', label: 'SHOTS / GM', title: 'Shots on goal per game (#1 = most)' },
  { key: 'pp', label: 'POWER PLAY', title: 'Power play % (#1 = best)' },
]
const DEF: { key: RK; label: string; title: string }[] = [
  { key: 'ga', label: 'GOALS ALLOWED / GM', title: 'Goals allowed per game (#1 = allows the most)' },
  { key: 'sa', label: 'SHOTS ALLOWED / GM', title: 'Shots allowed per game (#1 = allows the most)' },
  { key: 'pk', label: 'PENALTY KILL', title: 'Penalty kill % (#1 = best kill)' },
]
const LEAD: { key: StatKey; label: string; line: number }[] = [
  { key: 'p', label: 'POINTS', line: 0.5 },
  { key: 'g', label: 'GOALS', line: 0.5 },
  { key: 'a', label: 'ASSISTS', line: 0.5 },
  { key: 'sog', label: 'SHOTS ON GOAL', line: 2.5 },
]
const UNAVAILABLE = new Set(['OUT', 'IR', 'LTIR'])

function fmt(key: RK, v: number | null | undefined): string {
  if (v == null) return '—'
  if (key === 'pp' || key === 'pk') return `${v.toFixed(1)}%`
  if (key === 'sf' || key === 'sa') return v.toFixed(1)
  return v.toFixed(2)
}

function StatRow({ cols, r, label, sub }: { cols: typeof OFF; r: RateBlock | undefined; label: string; sub: string }) {
  return (
    <div className="mu-row">
      <div className="mu-row-lbl">
        <b>{label}</b>
        <small>{sub}</small>
      </div>
      <div className="mu-tiles">
        {cols.map((c) => {
          const rk = r?.[`${c.key}_rk`] ?? null
          return (
            <div key={c.key} className={`mu-tile ${chipTone(c.key, rk)}`} title={c.title}>
              <i>{c.label}</i>
              <b>{fmt(c.key, r?.[c.key])}</b>
              <span>{rk == null ? '–' : `#${rk}`}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Leaders({ block, out, onProps }: { block: LeaderBlock | undefined; out: Set<string>; onProps?: PropsOpener }) {
  if (!block) return <div className="mu-empty">Leaders aren't in this board (built before splits existed).</div>
  return (
    <div className="mu-leaders">
      {LEAD.map((c) => {
        const rows = (block[c.key] ?? []).slice(0, 3)
        return (
          <div key={c.key} className="mu-lead">
            <div className="mu-lead-h">{c.label}</div>
            {rows.length === 0 && <div className="mu-lead-none">none in this cut</div>}
            {rows.map((p, i) => (
              <button
                key={p.id}
                type="button"
                className={`mu-lead-row${i === 0 ? ' top' : ''}`}
                title={`${p.name}: ${p.v} in ${p.gp} games (${(p.v / p.gp).toFixed(2)} per game). Click for his game log.`}
                disabled={!onProps}
                onClick={() => onProps?.({ players: [p.id], stat: c.key, line: c.line })}
              >
                <span className="nm">
                  {p.name}
                  {out.has(p.name) && <em>OUT</em>}
                </span>
                <span className="v">{p.v}</span>
                <span className="pg">
                  {(p.v / p.gp).toFixed(2)}/gm · {p.gp} GP
                </span>
              </button>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function TeamHead({ team, side, xg, xgTone }: { team: TeamSide; side: 'away' | 'home'; xg: number | null; xgTone: string }) {
  const st = team.goalie_status
  const cls = st === 'Confirmed' ? 'ok' : st === 'Likely' || st === 'Expected' ? 'likely' : ''
  return (
    <div className={`mu-team ${side}`} style={{ ['--team-accent' as string]: team.color }}>
      <img src={LOGO(team.abbr)} alt={`${team.city} ${team.name} logo`} />
      <div>
        <div className="mu-side">{side === 'away' ? 'AWAY' : 'HOME'}</div>
        <h2>
          {team.city} <span>{team.name}</span>
        </h2>
        <div className="mu-rec">
          {team.record}
          {team.b2b && <span className="status-badge b2b">B2B</span>}
          {xg != null && (
            <span className={`xg ${xgTone}`} title="Market-implied expected goals tonight (vig removed; total split by the moneyline)">
              xG {xg.toFixed(2)}
            </span>
          )}
        </div>
        <div className="goalie-line" title={team.goalie_news ?? undefined}>
          🥅 <b>{team.goalie ?? 'TBD'}</b> <span className={cls}>{st ?? 'unconfirmed'}</span>
        </div>
      </div>
    </div>
  )
}

function Panel({ board, game, side, sel, onProps }: { board: Board; game: Game; side: 'away' | 'home'; sel: SplitSel; onProps?: PropsOpener }) {
  const team = game[side]
  const oppSide = side === 'away' ? 'home' : 'away'
  const opp = game[oppSide]
  const mine = ratesFor(board, team, side, sel)
  const theirs = ratesFor(board, opp, oppSide, sel)
  const own = sel.defense === 'own'
  const lu = game.lineup?.[side]
  const out = new Set((lu?.injuries ?? []).filter((i) => UNAVAILABLE.has((i.status ?? '').toUpperCase())).map((i) => i.player))
  return (
    <section className="mu-panel" style={{ ['--team-accent' as string]: team.color }} aria-label={`${team.abbr} ${cutLabel(sel, side)}`}>
      <header className="mu-panel-h">
        <img src={LOGO(team.abbr)} alt="" />
        <b>{team.abbr}</b>
        <span className="mu-cut">{cutLabel(sel, side)}</span>
        <span className="mu-gp">
          {mine?.gp ?? 0} GP{mine?.rec ? ` · ${mine.rec}` : ''}
        </span>
      </header>
      {mine && !mine.gp ? (
        <div className="mu-empty">No games in this cut yet.</div>
      ) : (
        <>
          <StatRow cols={OFF} r={mine} label={`${team.abbr} OFFENSE`} sub="green = scoring" />
          {own ? (
            <StatRow cols={DEF} r={mine} label={`${team.abbr} DEFENSE`} sub={`green = leaky, good for ${opp.abbr}`} />
          ) : (
            <StatRow cols={DEF} r={theirs} label={`${opp.abbr} DEFENSE`} sub={`${cutLabel(sel, oppSide)} · green = leaky, good for ${team.abbr}`} />
          )}
        </>
      )}
      <div className="mu-sec">
        {team.abbr} LEADERS <span>/ {cutLabel(sel, side)} · TOTAL, PER GAME</span>
      </div>
      <Leaders block={leadersFor(board, team.abbr, side, sel)} out={out} onProps={onProps} />
    </section>
  )
}

interface Props {
  board: Board
  gameId: string | null
  onPick: (id: string) => void
  sel: SplitSel
  onSel: (s: SplitSel) => void
  onBack: () => void
  onLineups?: (id: string) => void
  onProps?: PropsOpener
}

export function MatchupPage({ board, gameId, onPick, sel, onSel, onBack, onLineups, onProps }: Props) {
  if (!board.games.length) return <div className="state-box" style={{ marginTop: 40 }}>No NHL games on {longDate(board.date)}.</div>
  const idx = Math.max(0, board.games.findIndex((g) => g.id === gameId))
  const game = board.games[idx]
  const { away, home } = game
  const prev = board.games[idx - 1]
  const next = board.games[idx + 1]
  return (
    <div className="mu">
      <div className="mu-bar">
        <button type="button" className="mu-back" onClick={onBack}>
          ← Board
        </button>
        <div className="mu-nav">
          <button type="button" disabled={!prev} onClick={() => prev && onPick(prev.id)} aria-label="Previous game">
            ‹
          </button>
          <select className="lu-pick" aria-label="Choose game" value={game.id} onChange={(e) => onPick(e.target.value)}>
            {board.games.map((g) => (
              <option key={g.id} value={g.id}>
                {g.away.abbr} @ {g.home.abbr} · {etTime(g.start_utc)} ET
              </option>
            ))}
          </select>
          <button type="button" disabled={!next} onClick={() => next && onPick(next.id)} aria-label="Next game">
            ›
          </button>
        </div>
        {onLineups && (
          <button type="button" className="mu-back" onClick={() => onLineups(game.id)}>
            Lineups ↗
          </button>
        )}
      </div>

      <section className="mu-hero">
        <TeamHead team={away} side="away" xg={game.market?.xg_away ?? null} xgTone={game.market?.xg_tone_away ?? ''} />
        <div className="mu-mid">
          <div className="mu-when">
            {longDate(board.date).toUpperCase()} · {etTime(game.start_utc)} ET
          </div>
          <div className="mu-venue">{game.venue}</div>
          {game.smash?.flag && (
            <span className={`status-badge smash ${game.smash.kind === 'side' ? 'side' : 'all'}`} title={game.smash.why}>
              {game.smash.kind === 'side' ? `SMASH ${game.smash.side}` : 'SMASH · ALL-AROUND'}
            </span>
          )}
          <TotalsBar game={game} />
        </div>
        <TeamHead team={home} side="home" xg={game.market?.xg_home ?? null} xgTone={game.market?.xg_tone_home ?? ''} />
      </section>

      <div className="split-bar">
        <SplitToggles sel={sel} onChange={onSel} hasSplits={!!board.splits} />
        <span className="split-hint">Ranks are among all 32 teams within the selected cut. Small cuts (L5, L5 home/away) swing hard.</span>
      </div>

      <div className="mu-grid">
        <Panel board={board} game={game} side="away" sel={sel} onProps={onProps} />
        <Panel board={board} game={game} side="home" sel={sel} onProps={onProps} />
      </div>

      <section className="mu-plays">
        <div className="mu-sec">
          TOP PLAYS <span>/ OUR FAIR PRICE</span>
        </div>
        <div className="play-stack">
          {board.default_slots.map((lens, i) => {
            const play = playFor(game, lens)
            const t = play && onProps ? propsFor(play, lens) : null
            return <PlayRow key={lens} play={play} rank={i + 1} lensLabel={board.lenses[lens]} onClick={t ? () => onProps!(t) : undefined} />
          })}
        </div>
      </section>
    </div>
  )
}
