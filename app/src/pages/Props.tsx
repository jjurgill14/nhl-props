import { useEffect, useMemo, useState } from 'react'
import type { Board, GameLogRow, PlayerLog, StatKey } from '../data/types'
import { LOGO, loadPlayer } from '../data/load'

const STATS: { key: StatKey; label: string; lines: number[] }[] = [
  { key: 'g', label: 'Goals', lines: [0.5, 1.5] },
  { key: 'a', label: 'Assists', lines: [0.5, 1.5] },
  { key: 'p', label: 'Points', lines: [0.5, 1.5, 2.5] },
  { key: 'sog', label: 'Shots on Goal', lines: [1.5, 2.5, 3.5, 4.5] },
]

const PALETTE = ['#4ade80', '#60a5fa', '#f0bd81']

function shortDate(ymd: string): string {
  const [, m, d] = ymd.split('-').map(Number)
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} ${d}`
}

interface Series {
  player: PlayerLog
  rows: GameLogRow[] // last N, aligned to `games` (null-filled when a player missed one)
}

export interface PropsTarget {
  players: number[]
  stat?: StatKey
  line?: number
}

interface Props {
  board: Board
  target: PropsTarget
  onChange: (t: PropsTarget) => void
}

export function PropsPage({ board, target, onChange }: Props) {
  const [logs, setLogs] = useState<Record<number, PlayerLog | 'error'>>({})
  const [stat, setStat] = useState<StatKey>(target.stat ?? 'p')
  const [n, setN] = useState<5 | 10>(10)
  const [line, setLine] = useState<number>(target.line ?? 0.5)

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
    if (!statDef.lines.includes(line)) setLine(statDef.lines[0])
  }, [stat, statDef, line])

  const players = target.players.map((id) => logs[id]).filter((p): p is PlayerLog => !!p && p !== 'error')
  const loading = target.players.some((id) => !logs[id])
  const failed = target.players.filter((id) => logs[id] === 'error')

  // Game axis: for one player, their last N games. For a pair, the last N games BOTH played (shared game_ids).
  const games = useMemo(() => {
    if (!players.length) return [] as GameLogRow[]
    if (players.length === 1) return players[0].log.slice(-n)
    const shared = players.slice(1).reduce((acc, p) => {
      const ids = new Set(p.log.map((r) => r.game_id))
      return acc.filter((r) => ids.has(r.game_id))
    }, players[0].log)
    return shared.slice(-n)
  }, [players, n])

  const series: Series[] = players.map((p) => ({
    player: p,
    rows: games.map((g) => p.log.find((r) => r.game_id === g.game_id)!),
  }))

  const hit = (r: GameLogRow) => r[stat] > line
  const maxVal = Math.max(1, ...series.flatMap((s) => s.rows.map((r) => r[stat])))
  const yMax = Math.max(3, maxVal)

  if (!target.players.length) return <div className="state-box">Pick a player from the lineup or a play on the board.</div>
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
    for (let i = 0; i < len; i++) if (sets.every((rows) => hit(rows[rows.length - len + i]))) k++
    return [k, len] as const
  }
  const rate = (rows: GameLogRow[]) => [rows.filter(hit).length, rows.length] as const
  const avg = (rows: GameLogRow[]) => (rows.length ? (rows.reduce((a, r) => a + r[stat], 0) / rows.length).toFixed(1) : '–')
  const pct = ([k, m]: readonly [number, number]) => (m ? `${Math.round((100 * k) / m)}%` : '–')
  const pair = series.length > 1

  return (
    <>
      <section className="hero pr-hero">
        <div>
          <div className="eyebrow">NHL / PLAYER PROPS{pair ? ' · CORRELATED' : ''}</div>
          <h1>
            {lead.name.split(' ').slice(-1)[0]}
            {pair ? ` + ${players[1].name.split(' ').slice(-1)[0]}` : ''} <span>props.</span>
          </h1>
          <p>{pair ? 'Shared games only — both players dressed. Hit = each clears the line in the same game.' : 'Player props trends, form, and key numbers to inform your bets.'}</p>
        </div>
        <div className="pr-cards">
          {players.map((p) => {
            const t = teamOf(p.team)
            return (
              <div className="pr-card" key={p.id} style={{ ['--team-accent' as string]: t?.color ?? '#69cbd1' }}>
                <img src={LOGO(p.team)} alt="" />
                <div>
                  <b>{p.name}</b>
                  <small>
                    {({ L: 'LW', R: 'RW', C: 'C', D: 'D' } as Record<string, string>)[p.pos ?? ''] ?? p.pos ?? '–'} <span className="sep">|</span> #{p.jersey ?? '–'} <span className="sep">|</span>{' '}
                    {t ? `${t.city} ${t.name}`.toUpperCase() : p.team}
                  </small>
                </div>
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
            <div className="stat"><div className="stat-label">L10 both over {line}</div><div className="stat-main"><span className="stat-value">{bothHit(l10).join('/')}</span><span className="stat-suffix">({pct(bothHit(l10))})</span></div></div>
            <div className="stat"><div className="stat-label">L5 both over {line}</div><div className="stat-main"><span className="stat-value">{bothHit(l5).join('/')}</span><span className="stat-suffix">({pct(bothHit(l5))})</span></div></div>
            <div className="stat"><div className="stat-label">Independent (product)</div><div className="stat-main"><span className="stat-value">{pct([Math.round(1000 * l10.reduce((acc, rows) => acc * (rate(rows)[0] / Math.max(1, rows.length)), 1)), 1000])}</span><span className="stat-suffix">L10 rates multiplied</span></div></div>
            <div className="stat"><div className="stat-label">Shared games</div><div className="stat-main"><span className="stat-value">{games.length}</span><span className="stat-suffix">both dressed (any line)</span></div></div>
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
            <button key={l} className={line === l ? 'selected' : ''} aria-pressed={line === l} onClick={() => setLine(l)}>
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
      </div>

      <section className="pr-chart">
        <header>
          <h2>
            {title} — {statDef.label} per Game (Last {games.length})
          </h2>
          <span className="tag pr-tag">
            {statDef.label.toUpperCase()} — OVER {line}
          </span>
        </header>
        <Chart games={games} series={series} stat={stat} line={line} yMax={yMax} />
      </section>

      <section className="pr-log">
        <div className="pr-log-head">
          <h3>
            GAME LOG (LAST {games.length}) — {statDef.label.toUpperCase()}
          </h3>
          <span className="pr-legend">
            <i style={{ background: '#4ade80' }} /> Over {line} (Hit) <i style={{ background: '#f87171' }} /> Under {line} (Miss)
          </span>
        </div>
        <div className="pr-log-row">
          {games.map((g, i) => (
            <div className="pr-game" key={g.game_id}>
              <div className="pr-date">
                {shortDate(g.date)}
                <br />
                {g.home ? 'vs' : '@'} {g.opp}
              </div>
              {series.map((s, si) => {
                const r = s.rows[i]
                return (
                  <div key={si} className={`pr-pill ${hit(r) ? 'hit' : 'miss'}`} title={s.player.name}>
                    {pair && <small>{s.player.name.split(' ').slice(-1)[0].slice(0, 3).toUpperCase()} </small>}
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

function Chart({ games, series, stat, line, yMax }: { games: GameLogRow[]; series: Series[]; stat: StatKey; line: number; yMax: number }) {
  const W = 1200, H = 300, L = 44, R = 90, T = 28, B = 56
  const iw = W - L - R, ih = H - T - B
  const n = Math.max(1, games.length)
  const slot = iw / n
  const k = series.length
  const bw = Math.min(90, (slot * 0.72) / k)
  const y = (v: number) => T + ih - (v / yMax) * ih
  const ticks = Array.from({ length: Math.ceil(yMax) + 1 }, (_, i) => i)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pr-svg" role="img" aria-label={`${stat} per game`}>
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
              const isHit = v > line
              const fill = k === 1 ? (isHit ? '#4ade80' : '#f87171') : isHit ? PALETTE[si] : '#5b3a3a'
              return (
                <g key={si}>
                  <rect x={x} y={v === 0 ? T + ih - 4 : y(v)} width={bw - 4} height={v === 0 ? 4 : h} rx="2" fill={fill} opacity={v === 0 ? 0.7 : 1} />
                  <text x={x + (bw - 4) / 2} y={(v === 0 ? T + ih - 4 : y(v)) - 7} fill="#e6edf3" fontSize="14" fontWeight="700" textAnchor="middle">{v}</text>
                </g>
              )
            })}
            <text x={cx} y={T + ih + 20} fill="#c9d7e0" fontSize="13" textAnchor="middle">{shortDate(g.date)}</text>
            <text x={cx} y={T + ih + 38} fill="#c9d7e0" fontSize="13" textAnchor="middle">{g.home ? 'vs' : '@'} {g.opp}</text>
          </g>
        )
      })}
      <line x1={L} x2={W - R} y1={y(line)} y2={y(line)} stroke="#f0bd81" strokeWidth="2" strokeDasharray="8 6" />
      <rect x={W - R + 6} y={y(line) - 12} width={R - 10} height="24" rx="6" fill="#3a2a14" stroke="#f0bd81" />
      <text x={W - R + 6 + (R - 10) / 2} y={y(line) + 4} fill="#f0bd81" fontSize="11" fontWeight="800" textAnchor="middle">Prop line: {line}</text>
    </svg>
  )
}
