import { useEffect, useMemo, useState } from 'react'
import type { Board, GameLogRow, PlayerLog, StatKey } from '../data/types'
import { LOGO, loadPlayer } from '../data/load'
import { chipTone } from '../components/RankStrip'
import { PlayerSearch } from '../components/PlayerSearch'

const STATS: { key: StatKey; label: string; lines: number[] }[] = [
  { key: 'g', label: 'Goals', lines: [0.5, 1.5] },
  { key: 'a', label: 'Assists', lines: [0.5, 1.5] },
  { key: 'p', label: 'Points', lines: [0.5, 1.5, 2.5] },
  { key: 'sog', label: 'Shots on Goal', lines: [1.5, 2.5, 3.5, 4.5] },
]

function shortDate(ymd: string): string {
  const [, m, d] = ymd.split('-').map(Number)
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} ${d}`
}

/** 'W 4-2 OT' / 'L 1-3' for the player's team */
function scoreLabel(r: GameLogRow): string {
  if (r.tf == null || r.ta == null) return ''
  const res = r.tf > r.ta ? 'W' : 'L'
  return `${res} ${r.tf}-${r.ta}${r.ot && r.ot !== 'REG' ? ' ' + r.ot : ''}`
}

/** opponent's current rank in the stat they ALLOW that matters for this bet type */
function oppRank(board: Board, opp: string, stat: StatKey): { label: string; rk: number | null; tone: string } {
  const r = board.team_rates?.[opp]
  if (!r) return { label: '', rk: null, tone: '' }
  if (stat === 'sog') return { label: 'SA', rk: r.sa_rk, tone: chipTone('sa', r.sa_rk) }
  return { label: 'GA', rk: r.ga_rk, tone: chipTone('ga', r.ga_rk) }
}

interface Series {
  player: PlayerLog
  rows: GameLogRow[] // last N, aligned to `games` (null-filled when a player missed one)
  line: number
}

export interface PropsTarget {
  players: number[]
  stat?: StatKey
  line?: number
  /** Order players best-first (L10 hit rate at the line) once their logs have loaded. */
  sort?: 'best'
}

interface Props {
  board: Board
  target: PropsTarget
  onChange: (t: PropsTarget) => void
  searchFocus?: boolean
}

export function PropsPage({ board, target, onChange, searchFocus }: Props) {
  const [logs, setLogs] = useState<Record<number, PlayerLog | 'error'>>({})
  const [stat, setStat] = useState<StatKey>(target.stat ?? 'p')
  const [n, setN] = useState<5 | 10>(10)
  const [line, setLine] = useState<number>(target.line ?? 0.5)
  // Per-player overrides (Pastrnak 1.5 next to Zacha 0.5). The LINE control sets everyone; a tile sets one.
  const [lines, setLines] = useState<Record<number, number>>({})
  const lineFor = (id: number) => lines[id] ?? line
  const setAllLines = (l: number) => {
    setLine(l)
    setLines({})
    // clicking a line re-ranks the tiles: best hit rate at that line first
    onChange({ ...target, line: l, sort: 'best' })
  }
  const [dragId, setDragId] = useState<number | null>(null)
  const moveTo = (from: number, to: number) => {
    if (from === to) return
    const ids = target.players.filter((x) => x !== from)
    const at = ids.indexOf(to)
    ids.splice(at + (target.players.indexOf(from) < target.players.indexOf(to) ? 1 : 0), 0, from)
    onChange({ ...target, players: ids })
  }
  const [venue, setVenue] = useState<'all' | 'home' | 'away'>('all')

  useEffect(() => {
    for (const id of target.players) {
      if (logs[id]) continue
      loadPlayer(id)
        .then((p) => setLogs((l) => ({ ...l, [id]: p })))
        .catch(() => setLogs((l) => ({ ...l, [id]: 'error' })))
    }
  }, [target.players, logs])

  const statDef = STATS.find((s) => s.key === stat)!
  useEffect(() => {
    if (target.sort !== 'best') return
    const loaded = target.players.map((id) => logs[id]).filter((p): p is PlayerLog => !!p && p !== 'error')
    if (loaded.length < target.players.length) return
    const l = target.line ?? line
    const score = (p: PlayerLog) => {
      const last = p.log.slice(-10)
      return last.length ? last.filter((r) => r[stat] > l).length / last.length + last.length / 1000 : -1
    }
    const ordered = [...loaded].sort((a, b) => score(b) - score(a)).map((p) => p.id)
    onChange({ ...target, players: ordered, sort: undefined })
  }, [target, logs, stat, line, onChange])
  useEffect(() => {
    if (!statDef.lines.includes(line)) setAllLines(statDef.lines[0])
  }, [stat, statDef, line])

  const players = target.players.map((id) => logs[id]).filter((p): p is PlayerLog => !!p && p !== 'error')
  const loading = target.players.some((id) => !logs[id])
  const failed = target.players.filter((id) => logs[id] === 'error')

  // Game axis: for one player, their last N games. For a pair, the last N games BOTH played (shared game_ids).
  const games = useMemo(() => {
    if (!players.length) return [] as GameLogRow[]
    const byVenue = (rows: GameLogRow[]) => (venue === 'all' ? rows : rows.filter((r) => (venue === 'home') === r.home))
    if (players.length === 1) return byVenue(players[0].log).slice(-n)
    const shared = players.slice(1).reduce((acc, p) => {
      const ids = new Set(p.log.map((r) => r.game_id))
      return acc.filter((r) => ids.has(r.game_id))
    }, players[0].log)
    return byVenue(shared).slice(-n)
  }, [players, n, venue])

  const series: Series[] = players.map((p) => ({
    player: p,
    line: lineFor(p.id),
    rows: games.map((g) => p.log.find((r) => r.game_id === g.game_id)!),
  }))

  const hitAt = (r: GameLogRow, l: number) => r[stat] > l
  const pair = players.length > 1
  const code = (p: PlayerLog) => p.name.split(' ').slice(-1)[0].slice(0, 3).toUpperCase()
  const maxVal = Math.max(1, ...series.flatMap((s) => s.rows.map((r) => r[stat])))
  const yMax = Math.max(3, maxVal)

  if (!target.players.length)
    return (
      <section className="hero" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
        <div className="eyebrow">NHL / PLAYER PROPS</div>
        <h1>
          Find a <span>player.</span>
        </h1>
        <p>Any skater who has dressed this season, any team. Type a name or a team code.</p>
        <div style={{ width: 'min(520px, 100%)', marginTop: 14 }}>
          <PlayerSearch onPick={(id) => onChange({ players: [id], stat: 'p', line: 0.5 })} autoFocus={searchFocus} />
        </div>
      </section>
    )
  if (loading && !players.length) return <div className="state-box">Loading game log…</div>
  if (failed.length && !players.length) return <div className="state-box err">No game log for this player yet.</div>

  const lead = players[0]
  const teamOf = (abbr: string) => board.games.flatMap((g) => [g.away, g.home]).find((t) => t.abbr === abbr)
  const title = players.map((p) => p.name).join(' + ')

  // Tiles
  const l10 = series.map((s) => s.rows.slice(-10))
  const l5 = series.map((s) => s.rows.slice(-5))
  const bothHit = (sets: GameLogRow[][]) => {
    const len = Math.min(...sets.map((r) => r.length))
    let k = 0
    for (let i = 0; i < len; i++) if (sets.every((rows, si) => hitAt(rows[rows.length - len + i], series[si].line))) k++
    return [k, len] as const
  }
  const rate = (rows: GameLogRow[], l = line) => [rows.filter((r) => hitAt(r, l)).length, rows.length] as const
  const mixed = pair && series.some((s) => s.line !== series[0].line)
  const lineLabel = mixed ? series.map((s) => `${code(s.player)} ${s.line}`).join(' · ') : String(line)
  const avg = (rows: GameLogRow[]) => (rows.length ? (rows.reduce((a, r) => a + r[stat], 0) / rows.length).toFixed(1) : '–')
  const pct = ([k, m]: readonly [number, number]) => (m ? `${Math.round((100 * k) / m)}%` : '–')
  const MAXP = 3
  const canAdd = target.players.length < MAXP

  return (
    <>
      <section className="hero pr-hero">
        <div>
          <div className="eyebrow">NHL / PLAYER PROPS{pair ? ' · CORRELATED' : ''}</div>
          <h1>
            {lead.name.split(' ').slice(-1)[0]}
            {players.slice(1).map((p) => ` + ${p.name.split(' ').slice(-1)[0]}`).join('')} <span>props.</span>
          </h1>
          <p>{pair ? `Shared games only — ${players.length === 3 ? 'all three' : 'both'} dressed. Hit = each clears the line in the same game.` : 'Player props trends, form, and key numbers to inform your bets.'}</p>
        </div>
        <div className={`pr-cards${pair ? ' stack' : ''}`}>
          <div className="pr-search-slot">
            <PlayerSearch
              placeholder={canAdd ? `Add a player… (${target.players.length}/${MAXP} — a pair or a full line)` : 'Replace the last player…'}
              onPick={(id) => { if (target.players.includes(id)) return; onChange({ ...target, players: canAdd ? [...target.players, id] : [...target.players.slice(0, MAXP - 1), id] }) }}
            />
          </div>
          {players.map((p, pi) => {
            const t = teamOf(p.team)
            return (
              <div
                className={`pr-card${pair ? ' compact' : ''}${dragId === p.id ? ' dragging' : ''}`}
                key={p.id}
                style={{ ['--team-accent' as string]: t?.color ?? '#69cbd1' }}
                draggable={pair}
                title={pair ? 'Drag to reorder' : undefined}
                onDragStart={(e) => {
                  setDragId(p.id)
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragOver={(e) => {
                  if (dragId != null && dragId !== p.id) e.preventDefault()
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  if (dragId != null) moveTo(dragId, p.id)
                  setDragId(null)
                }}
                onDragEnd={() => setDragId(null)}
              >
                {pair && <span className="pr-grip" aria-hidden="true">⋮⋮</span>}
                {pair && (
                  <span className="pr-key" title={`${p.name}'s bars`}>
                    <Swatch idx={pi} />
                    <b>{code(p)}</b>
                  </span>
                )}
                <img src={LOGO(p.team)} alt="" />
                <div>
                  <b>{p.name}</b>
                  <small>
                    {({ L: 'LW', R: 'RW', C: 'C', D: 'D' } as Record<string, string>)[p.pos ?? ''] ?? p.pos ?? '–'} <span className="sep">|</span> #{p.jersey ?? '–'} <span className="sep">|</span>{' '}
                    {t ? `${t.city} ${t.name}`.toUpperCase() : p.team}
                  </small>
                </div>
                {pair && (
                  <div className="pr-line-pick demo-switch" title="This player's line">
                    {statDef.lines.map((l) => (
                      <button key={l} className={lineFor(p.id) === l ? 'selected' : ''} aria-pressed={lineFor(p.id) === l} onClick={() => setLines((m) => ({ ...m, [p.id]: l }))}>
                        {l}
                      </button>
                    ))}
                  </div>
                )}
                {pair && (
                  <button className="pr-remove" title="Remove from view" onClick={() => onChange({ ...target, players: target.players.filter((x) => x !== p.id) })}>
                    ×
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section className="summary pr-tiles">
        {pair ? (
          <>
            <div className="stat"><div className="stat-label">L10 {players.length === 3 ? 'all three' : 'both'} over {lineLabel}</div><div className="stat-main"><span className="stat-value">{bothHit(l10).join('/')}</span><span className="stat-suffix">({pct(bothHit(l10))})</span></div></div>
            <div className="stat"><div className="stat-label">L5 {players.length === 3 ? 'all three' : 'both'} over {lineLabel}</div><div className="stat-main"><span className="stat-value">{bothHit(l5).join('/')}</span><span className="stat-suffix">({pct(bothHit(l5))})</span></div></div>
            <div className="stat"><div className="stat-label">Independent (product)</div><div className="stat-main"><span className="stat-value">{pct([Math.round(1000 * l10.reduce((acc, rows, si) => acc * (rate(rows, series[si].line)[0] / Math.max(1, rows.length)), 1)), 1000])}</span><span className="stat-suffix">L10 rates multiplied</span></div></div>
            <div className="stat"><div className="stat-label">Shared games</div><div className="stat-main"><span className="stat-value">{games.length}</span><span className="stat-suffix">{players.length === 3 ? 'all three' : 'both'} dressed (any line)</span></div></div>
          </>
        ) : (
          <>
            <div className="stat"><div className="stat-label">L10 over {line} hit rate</div><div className="stat-main"><span className="stat-value">{rate(l10[0]).join('/')}</span><span className="stat-suffix">({pct(rate(l10[0]))})</span></div></div>
            <div className="stat"><div className="stat-label">L5 over {line} hit rate</div><div className="stat-main"><span className="stat-value">{rate(l5[0]).join('/')}</span><span className="stat-suffix">({pct(rate(l5[0]))})</span></div></div>
            <div className="stat"><div className="stat-label">L10 average {statDef.label.toLowerCase()}</div><div className="stat-main"><span className="stat-value">{avg(l10[0])}</span></div></div>
            <div className="stat"><div className="stat-label">Most recent game</div><div className="stat-main"><span className="stat-value">{l10[0].at(-1)?.[stat] ?? '–'}</span><span className="stat-suffix">{statDef.label.toLowerCase()}</span></div></div>
          </>
        )}
      </section>

      <div className="pr-controls">
        <span className="pr-lbl">BET TYPE</span>
        <div className="demo-switch">
          {STATS.map((s) => (
            <button key={s.key} className={stat === s.key ? 'selected' : ''} aria-pressed={stat === s.key} onClick={() => setStat(s.key)}>
              {s.label}
            </button>
          ))}
        </div>
        <span className="pr-lbl">LINE</span>
        <div className="demo-switch">
          {statDef.lines.map((l) => (
            <button key={l} className={line === l ? 'selected' : ''} aria-pressed={line === l} onClick={() => setAllLines(l)}>
              {l}
            </button>
          ))}
        </div>
        <span className="pr-sep" />
        <span className="pr-lbl">SAMPLE SIZE</span>
        <div className="demo-switch">
          {([5, 10] as const).map((k) => (
            <button key={k} className={n === k ? 'selected' : ''} aria-pressed={n === k} onClick={() => setN(k)}>
              L{k}
            </button>
          ))}
        </div>
        <span className="pr-sep" />
        <span className="pr-lbl">VENUE</span>
        <div className="demo-switch">
          {(
            [
              ['all', 'All'],
              ['home', 'Home'],
              ['away', 'Away'],
            ] as const
          ).map(([k, label]) => (
            <button key={k} className={venue === k ? 'selected' : ''} aria-pressed={venue === k} onClick={() => setVenue(k)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <section className="pr-chart">
        <header>
          <h2>
            {title} — {statDef.label} per Game (Last {games.length}{venue === 'all' ? '' : venue === 'home' ? ' home' : ' away'})
          </h2>
          <span className="tag pr-tag">
            {statDef.label.toUpperCase()} — OVER {line}
          </span>
        </header>
        <Chart games={games} series={series} stat={stat} yMax={yMax} board={board} />
      </section>

      <section className="pr-log">
        <div className="pr-log-head">
          <h3>
            GAME LOG (LAST {games.length}) — {statDef.label.toUpperCase()}
          </h3>
          <span className="pr-legend">
            <i style={{ background: '#4ade80' }} /> Over {line} (Hit) <i style={{ background: '#f87171' }} /> Under {line} (Miss)
            {pair &&
              players.map((p, i) => (
                <span key={p.id}>
                  {' '}· <Swatch idx={i} small /> <b>{code(p)}</b> {p.name.split(' ').slice(-1)[0]} (line {lineFor(p.id)})
                </span>
              ))}
          </span>
        </div>
        <div className="pr-log-row">
          {games.map((g, i) => (
            <div className="pr-game" key={g.game_id}>
              <div className="pr-date">
                {shortDate(g.date)}
                <br />
                {g.home ? 'vs' : '@'} {g.opp}
                <br />
                {(() => { const o = oppRank(board, g.opp, stat); return o.rk != null ? <span className={`pr-rk ${o.tone}`} style={{ marginLeft: 0, marginRight: 6 }}>{o.label} #{o.rk}</span> : null })()}
                <span className={g.tf != null && g.ta != null && g.tf > g.ta ? 'win' : 'loss'}>{scoreLabel(g)}</span>
              </div>
              {series.map((s, si) => {
                const r = s.rows[i]
                return (
                  <div key={si} className={`pr-pill ${hitAt(r, s.line) ? 'hit' : 'miss'}`} title={`${s.player.name} · line ${s.line}`}>
                    {pair && <small>{code(s.player)} </small>}
                    {r[stat]} {stat === 'sog' ? 'SOG' : stat === 'p' ? 'PTS' : stat === 'g' ? 'G' : 'A'}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
        <p className="pr-foot">This season only. Data: NHL boxscores through {games.at(-1)?.date ?? '–'}.</p>
      </section>
    </>
  )
}

// Bar fills per player slot: solid, diagonal stripes, dots. Hit/miss colour still carries the result,
// so the swatch is shown in "hit" green — it is the shape that identifies the player.
export function Swatch({ idx, small = false }: { idx: number; small?: boolean }) {
  const s = small ? 14 : 26
  const id = `sw-${idx}-${small ? 's' : 'l'}`
  return (
    <svg width={s} height={s} viewBox="0 0 26 26" className="pr-swatch" aria-hidden="true">
      <defs>
        <pattern id={`${id}-stripe`} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#14532d" />
          <rect width="3" height="6" fill="#4ade80" />
        </pattern>
        <pattern id={`${id}-dots`} patternUnits="userSpaceOnUse" width="6" height="6">
          <rect width="6" height="6" fill="#14532d" />
          <circle cx="3" cy="3" r="1.7" fill="#4ade80" />
        </pattern>
      </defs>
      <rect x="1" y="1" width="24" height="24" rx="5" fill={idx === 0 ? '#4ade80' : `url(#${id}-${idx === 1 ? 'stripe' : 'dots'})`} stroke="#4ade80" strokeWidth="1.5" />
    </svg>
  )
}

function Chart({ games, series, stat, yMax, board }: { games: GameLogRow[]; series: Series[]; stat: StatKey; yMax: number; board: Board }) {
  const code = (name: string) => name.split(' ').slice(-1)[0].slice(0, 3).toUpperCase()
  const dy = series.length > 1 ? 14 : 0
  const W = 1200, H = 340 + dy, L = 44, R = 90, T = 28, B = 96 + dy
  const TONE: Record<string, string> = { hot: '#4ade80', mid: '#f0bd81', cold: '#f87171', '': '#8fb0c0' }
  const iw = W - L - R, ih = H - T - B
  const n = Math.max(1, games.length)
  const slot = iw / n
  const k = series.length
  const bw = Math.min(90, (slot * 0.72) / k)
  const y = (v: number) => T + ih - (v / yMax) * ih
  const ticks = Array.from({ length: Math.ceil(yMax) + 1 }, (_, i) => i)
  // one dashed line per distinct prop line; labelled with the player codes when they differ
  const distinct = [...new Set(series.map((s) => s.line))].sort((a, b) => a - b)
  const propLines = distinct.map((value) => ({ value, who: distinct.length > 1 ? series.filter((s) => s.line === value).map((s) => code(s.player.name)).join('/') : '' }))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pr-svg" role="img" aria-label={`${stat} per game`}>
      <defs>
        <pattern id="stripe-hit" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="#14532d" />
          <rect width="4" height="8" fill="#4ade80" />
        </pattern>
        <pattern id="stripe-miss" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="#5b1f1f" />
          <rect width="4" height="8" fill="#f87171" />
        </pattern>
        <pattern id="dots-hit" patternUnits="userSpaceOnUse" width="8" height="8">
          <rect width="8" height="8" fill="#14532d" />
          <circle cx="4" cy="4" r="2.2" fill="#4ade80" />
        </pattern>
        <pattern id="dots-miss" patternUnits="userSpaceOnUse" width="8" height="8">
          <rect width="8" height="8" fill="#5b1f1f" />
          <circle cx="4" cy="4" r="2.2" fill="#f87171" />
        </pattern>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#1f3140" strokeWidth="1" />
          <text x={L - 10} y={y(t) + 4} fill="#8fb0c0" fontSize="13" textAnchor="end">{t}</text>
        </g>
      ))}
      <rect x={L} y={T} width={iw} height={ih} fill="none" stroke="#2a3d4c" />
      {games.map((g, i) => {
        const cx = L + slot * i + slot / 2
        return (
          <g key={g.game_id}>
            {series.map((s, si) => {
              const v = s.rows[i][stat]
              const x = cx - (bw * k) / 2 + bw * si + 2
              const h = Math.max(4, ih * (v / yMax))
              const isHit = v > s.line
              const base = isHit ? '#4ade80' : '#f87171'
              const fill = si === 0 ? base : `url(#${si === 1 ? 'stripe' : 'dots'}-${isHit ? 'hit' : 'miss'})`
              return (
                <g key={si}>
                  <title>{s.player.name}: {v}</title>
                  <rect x={x} y={v === 0 ? T + ih - 4 : y(v)} width={bw - 4} height={v === 0 ? 4 : h} rx="2" fill={fill} stroke={si === 0 ? 'none' : base} strokeWidth={si === 0 ? 0 : 1.5} opacity={v === 0 ? 0.7 : 1} />
                  <text x={x + (bw - 4) / 2} y={(v === 0 ? T + ih - 4 : y(v)) - 7} fill="#e6edf3" fontSize="14" fontWeight="700" textAnchor="middle">{v}</text>
                  {k > 1 && (
                    <text x={x + (bw - 4) / 2} y={T + ih + 12} fill="#8fb0c0" fontSize={k > 2 ? 9 : 10} fontWeight="800" textAnchor="middle" letterSpacing=".04em">{code(s.player.name)}</text>
                  )}
                </g>
              )
            })}
            <text x={cx} y={T + ih + 20 + dy} fill="#c9d7e0" fontSize="13" textAnchor="middle">{shortDate(g.date)}</text>
            <text x={cx} y={T + ih + 38 + dy} fill="#c9d7e0" fontSize="13" textAnchor="middle">{g.home ? 'vs' : '@'} {g.opp}</text>
            {(() => { const o = oppRank(board, g.opp, stat); return o.rk != null ? (
              <text x={cx} y={T + ih + 56 + dy} fill={TONE[o.tone]} fontSize="12" fontWeight="800" textAnchor="middle">{o.label} #{o.rk}</text>
            ) : null })()}
            <text x={cx} y={T + ih + 76 + dy} fill={g.tf != null && g.ta != null && g.tf > g.ta ? '#9de0b6' : '#f87171'} fontSize="12" fontWeight="700" textAnchor="middle">{scoreLabel(g)}</text>
          </g>
        )
      })}
      {propLines.map(({ value, who }, li) => (
        <g key={value}>
          <line x1={L} x2={W - R} y1={y(value)} y2={y(value)} stroke="#f4f7fa" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="0.1 6" />
          <rect x={W - R + 6} y={y(value) - 12 + (li % 2 ? 0 : 0)} width={R - 10} height="24" rx="6" fill="#1c2a38" stroke="#f4f7fa" />
          <text x={W - R + 6 + (R - 10) / 2} y={y(value) + 4} fill="#f4f7fa" fontSize={who ? 10 : 11} fontWeight="800" textAnchor="middle">{who ? `${who} ${value}` : `Prop line: ${value}`}</text>
        </g>
      ))}
    </svg>
  )
}
