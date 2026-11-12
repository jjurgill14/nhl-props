import { useMemo, useState } from 'react'
import type { Board } from '../data/types'
import { LOGO } from '../data/load'
import { chipTone } from '../components/RankStrip'

type Key = 'gf' | 'ga' | 'sf' | 'sa' | 'pp' | 'pk' | 'ppg' | 'ppga'

const COLS: { key: Key; label: string; fmt: (v: number | null) => string; goodIsLow: boolean; note: string }[] = [
  { key: 'gf', label: 'GF / G', fmt: (v) => (v == null ? '—' : v.toFixed(2)), goodIsLow: true, note: '#1 = most goals scored' },
  { key: 'ga', label: 'GA / G', fmt: (v) => (v == null ? '—' : v.toFixed(2)), goodIsLow: false, note: '#1 = allows the most' },
  { key: 'sf', label: 'SOG / G', fmt: (v) => (v == null ? '—' : v.toFixed(1)), goodIsLow: true, note: '#1 = most shots' },
  { key: 'sa', label: 'SOG ALLOWED / G', fmt: (v) => (v == null ? '—' : v.toFixed(1)), goodIsLow: false, note: '#1 = allows the most' },
  { key: 'pp', label: 'PP %', fmt: (v) => (v == null ? '—' : `${v.toFixed(1)}%`), goodIsLow: true, note: '#1 = best power play' },
  { key: 'pk', label: 'PK %', fmt: (v) => (v == null ? '—' : `${v.toFixed(1)}%`), goodIsLow: true, note: '#1 = best penalty kill' },
  { key: 'ppg', label: 'PPG / G', fmt: (v) => (v == null ? '—' : v.toFixed(2)), goodIsLow: true, note: 'PP goals for / game' },
  { key: 'ppga', label: 'PPGA / G', fmt: (v) => (v == null ? '—' : v.toFixed(2)), goodIsLow: false, note: 'PP goals allowed / game' },
]

export function TeamRatesPage({ board }: { board: Board }) {
  const [sort, setSort] = useState<Key>('gf')
  const tr = board.team_rates ?? {}
  const tonight = new Set(board.games.flatMap((g) => [g.away.abbr, g.home.abbr]))
  const rows = useMemo(
    () => Object.entries(tr).sort((a, b) => (a[1][`${sort}_rk`] ?? 99) - (b[1][`${sort}_rk`] ?? 99)),
    [tr, sort],
  )
  const col = COLS.find((c) => c.key === sort)!
  if (!rows.length) return <div className="state-box">No team rates in this board yet.</div>
  const anyPP = rows.some(([, r]) => r.pp != null)
  return (
    <>
      <section className="hero" style={{ alignItems: 'flex-start' }}>
        <div>
          <div className="eyebrow">NHL / TEAM RATES · {board.date}</div>
          <h1>
            Team <span>rankings.</span>
          </h1>
          <p>
            This season, all 32 teams, from our boxscores. Click a column to rank by it. Tonight's teams are highlighted. Ranked by{' '}
            <b style={{ color: '#9ff0ec' }}>{col.label}</b> — {col.note}.
          </p>
        </div>
      </section>
      <table className="tr-table">
        <thead>
          <tr>
            <th>TEAM</th>
            <th>GP</th>
            {COLS.map((c) => (
              <th key={c.key} className={sort === c.key ? 'on' : ''} onClick={() => setSort(c.key)} title={c.note}>
                {c.label} <small>rk</small>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([abbr, r]) => (
            <tr key={abbr} className={tonight.has(abbr) ? 'tonight' : ''}>
              <td>
                <img src={LOGO(abbr)} alt="" /> {r.city} {r.name}
                {tonight.has(abbr) && <small>TONIGHT</small>}
              </td>
              <td>{r.gp ?? '—'}</td>
              {COLS.map((c) => {
                const rk = r[`${c.key}_rk`]
                const tone = c.key === 'ppg' ? chipTone('gf', rk) : c.key === 'ppga' ? chipTone('ga', rk) : chipTone(c.key, rk)
                return (
                  <td key={c.key} className={tone}>
                    {c.fmt(r[c.key])}
                    <small>{rk == null ? '' : `#${rk}`}</small>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tr-note">
        Rank 1 = most, for every raw rate — so on GA and shots allowed, #1 is the leakiest team. One color rule: green = good for an
        offensive bet. Offense columns (GF, SOG, PP, PPG): green = bet this team's shooters. Defense columns (GA, SOG allowed, PK, PPGA):
        green = this team is leaky, so bet the other side's shooters. {!anyPP && 'PP% / PK% appear once the overnight job backfills power-play opportunities from the NHL game pages (pending).'}
      </p>
    </>
  )
}
