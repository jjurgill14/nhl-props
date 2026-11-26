import { useMemo, useState } from 'react'
import type { Board, RateBlock, SplitWindow } from '../data/types'
import { LOGO } from '../data/load'
import { WINDOW_OPTS } from '../data/splits'
import { tone, type ColorView, type Tone } from '../data/tiers'

type Key = 'gf' | 'ga' | 'sf' | 'sa' | 'pp' | 'pk'
type Venue = 'all' | 'home' | 'away'
type Dir = 'desc' | 'asc'

const pct = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`)
const two = (v: number | null) => (v == null ? '—' : v.toFixed(2))
const one = (v: number | null) => (v == null ? '—' : v.toFixed(1))

interface Col {
  key: Key
  label: string
  what: string
  fmt: (v: number | null) => string
  defense: boolean
  /** Top-5 card + sorted-column wording: [most-first, fewest-first] */
  most: string
  fewest: string
  mostTag: string
  fewestTag: string
}
const COLS: Col[] = [
  { key: 'gf', label: 'GF/G', what: 'Goals for per game', fmt: two, defense: false, most: 'MOST GOALS / GAME', fewest: 'FEWEST GOALS / GAME', mostTag: 'Highest scoring', fewestTag: 'Lowest scoring' },
  { key: 'ga', label: 'GA/G', what: 'Goals allowed per game', fmt: two, defense: true, most: 'MOST GOALS ALLOWED / GAME', fewest: 'FEWEST GOALS ALLOWED / GAME', mostTag: 'Leakiest', fewestTag: 'Stingiest' },
  { key: 'sf', label: 'SOG/G', what: 'Shots on goal per game', fmt: one, defense: false, most: 'MOST SHOTS / GAME', fewest: 'FEWEST SHOTS / GAME', mostTag: 'Most shots', fewestTag: 'Fewest shots' },
  { key: 'sa', label: 'SOG ALLOWED/G', what: 'Shots allowed per game', fmt: one, defense: true, most: 'MOST SHOTS ALLOWED / GAME', fewest: 'FEWEST SHOTS ALLOWED / GAME', mostTag: 'Most allowed', fewestTag: 'Fewest allowed' },
  { key: 'pp', label: 'PP %', what: 'Power play percentage', fmt: pct, defense: false, most: 'BEST POWER PLAY', fewest: 'WORST POWER PLAY', mostTag: 'Best', fewestTag: 'Worst' },
  { key: 'pk', label: 'PK %', what: 'Penalty kill percentage', fmt: pct, defense: true, most: 'BEST PENALTY KILL', fewest: 'WEAKEST PENALTY KILL', mostTag: 'Best', fewestTag: 'Weakest' },
]

// conference / division (2026-27 alignment)
const DIVS: Record<string, string[]> = {
  Atlantic: ['BOS', 'BUF', 'DET', 'FLA', 'MTL', 'OTT', 'TBL', 'TOR'],
  Metropolitan: ['CAR', 'CBJ', 'NJD', 'NYI', 'NYR', 'PHI', 'PIT', 'WSH'],
  Central: ['CHI', 'COL', 'DAL', 'MIN', 'NSH', 'STL', 'UTA', 'WPG'],
  Pacific: ['ANA', 'CGY', 'EDM', 'LAK', 'SEA', 'SJS', 'VAN', 'VGK'],
}
const CONF: Record<string, string[]> = { East: ['Atlantic', 'Metropolitan'], West: ['Central', 'Pacific'] }
const divOf = (abbr: string) => Object.keys(DIVS).find((d) => DIVS[d].includes(abbr)) ?? ''

/** Which end of a column is the green end in this view: 'desc' (most first) or 'asc'. */
function greenEnd(col: Col, view: ColorView): Dir {
  if (!col.defense) return 'desc'
  const leakyFirst: Dir = col.key === 'pk' ? 'asc' : 'desc' // a low kill % is the leaky one
  return view === 'betting' ? leakyFirst : leakyFirst === 'desc' ? 'asc' : 'desc'
}
const tagFor = (col: Col, dir: Dir) => (dir === 'desc' ? col.mostTag : col.fewestTag)
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}`

interface Row { abbr: string; city: string; name: string; r: RateBlock }

export function TeamRatesPage({ board }: { board: Board }) {
  // The color view always opens on Betting: this state lives and dies with the page.
  const [view, setView] = useState<ColorView>('betting')
  const [win, setWin] = useState<SplitWindow>('season')
  const [venue, setVenue] = useState<Venue>('all')
  const [conf, setConf] = useState<'all' | 'East' | 'West'>('all')
  const [div, setDiv] = useState<string>('all')
  const [sort, setSort] = useState<{ key: Key; dir: Dir }>({ key: 'ga', dir: 'desc' })

  const meta = board.team_rates ?? {}
  const hasSplits = !!board.splits
  const cut = `${win}|${venue}`
  const all: Row[] = useMemo(
    () =>
      Object.keys(meta)
        .map((abbr) => ({ abbr, city: meta[abbr].city, name: meta[abbr].name, r: (board.splits?.teams[abbr]?.[cut] ?? meta[abbr]) as RateBlock }))
        .filter((x) => x.r),
    [meta, board.splits, cut],
  )
  const tonight = new Set(board.games.flatMap((g) => [g.away.abbr, g.home.abbr]))
  const xg: Record<string, { v: number; tone: string; opp: string }> = {}
  for (const g of board.games) {
    if (g.market?.xg_away != null) xg[g.away.abbr] = { v: g.market.xg_away, tone: g.market.xg_tone_away, opp: `@ ${g.home.abbr}` }
    if (g.market?.xg_home != null) xg[g.home.abbr] = { v: g.market.xg_home, tone: g.market.xg_tone_home, opp: `vs ${g.away.abbr}` }
  }

  const shown = all.filter((x) => {
    const d = divOf(x.abbr)
    return (conf === 'all' || CONF[conf].includes(d)) && (div === 'all' || d === div)
  })
  const sorter = (key: Key, dir: Dir) => (a: Row, b: Row) => {
    const va = a.r[key], vb = b.r[key]
    if (va == null) return 1
    if (vb == null) return -1
    return dir === 'desc' ? vb - va : va - vb
  }
  const rows = [...shown].sort(sorter(sort.key, sort.dir))
  // bar length: where the value sits between the league's lowest and highest in this cut
  const span = (key: Key) => {
    const vs = all.map((x) => x.r[key]).filter((v): v is number => v != null)
    return { lo: Math.min(...vs), hi: Math.max(...vs) }
  }
  const sp = span(sort.key)

  if (!all.length) return <div className="state-box">No team rates in this board yet.</div>
  const cutText = `${win === 'season' ? 'SEASON' : win.toUpperCase()} · ${venue === 'all' ? 'ALL GAMES' : venue.toUpperCase()}`
  const defWord = view === 'betting' ? 'leaky' : 'stingy'

  return (
    <div className="tr">
      <section className="hero" style={{ alignItems: 'flex-start', marginBottom: 18 }}>
        <div>
          <div className="eyebrow">NHL / TEAM RANKINGS · {board.date}</div>
          <h1>
            Team <span className="tr-accent">Rankings</span>
          </h1>
          <p>
            All 32 teams from our boxscores. Colors are tiers: how far a team sits from the league average, so the outliers are the cells that glow.{' '}
            {view === 'betting'
              ? 'Betting view: green = good for an offensive bet, so a leaky defense is green.'
              : 'Team strength view: green = the team is good at it, so a stingy defense is green.'}
          </p>
        </div>
      </section>

      <div className="tr-cards">
        {COLS.map((c) => {
          const dir = greenEnd(c, view)
          const top = [...shown].sort(sorter(c.key, dir)).filter((x) => x.r[c.key] != null).slice(0, 5)
          const on = sort.key === c.key
          return (
            <button key={c.key} type="button" className={`tr-card${on ? ' on' : ''}`} title={`Sort the table: ${tagFor(c, dir).toLowerCase()} first`} onClick={() => setSort({ key: c.key, dir })}>
              <div className="tr-card-h">
                <b>
                  Top 5 – {c.label} <em>({tagFor(c, dir)})</em>
                </b>
                <small>{c.what}</small>
              </div>
              {top.map((x, i) => (
                <div key={x.abbr} className={`tr-card-row${i === 0 ? ' first' : ''}`}>
                  <span className="n">{i + 1}</span>
                  <img src={LOGO(x.abbr)} alt="" />
                  <span className="a">{x.abbr}</span>
                  <span className={`v ${tone(c.key, x.r[`${c.key}_t`], x.r[`${c.key}_rk`], view)}`}>{c.fmt(x.r[c.key])}</span>
                </div>
              ))}
            </button>
          )
        })}
      </div>

      <div className="tr-bar">
        <div className="seg" role="group" aria-label="Conference">
          {(['all', 'East', 'West'] as const).map((k) => (
            <button key={k} type="button" className={conf === k ? 'on' : ''} aria-pressed={conf === k} onClick={() => { setConf(k); setDiv('all') }}>
              {k === 'all' ? 'All Teams' : k}
            </button>
          ))}
        </div>
        <select className="lu-pick" aria-label="Division" value={div} onChange={(e) => setDiv(e.target.value)}>
          <option value="all">All Divisions</option>
          {Object.keys(DIVS).filter((d) => conf === 'all' || CONF[conf].includes(d)).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <div className="seg" role="group" aria-label="Window">
          <span className="seg-lbl">WINDOW</span>
          {WINDOW_OPTS.map((o) => (
            <button key={o.key} type="button" disabled={!hasSplits && o.key !== 'season'} className={win === o.key ? 'on' : ''} aria-pressed={win === o.key} onClick={() => setWin(o.key)}>
              {o.label}
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Venue">
          <span className="seg-lbl">VENUE</span>
          {(['all', 'home', 'away'] as const).map((k) => (
            <button key={k} type="button" disabled={!hasSplits && k !== 'all'} className={venue === k ? 'on' : ''} aria-pressed={venue === k} onClick={() => setVenue(k)}>
              {k === 'all' ? 'All' : k === 'home' ? 'Home' : 'Away'}
            </button>
          ))}
        </div>
        <div className="seg view" role="group" aria-label="Color view">
          <span className="seg-lbl">COLORS</span>
          <button type="button" className={view === 'betting' ? 'on' : ''} aria-pressed={view === 'betting'} title="Green = good for an offensive bet. Leaky defenses are green." onClick={() => setView('betting')}>
            Betting View
          </button>
          <button type="button" className={view === 'strength' ? 'on' : ''} aria-pressed={view === 'strength'} title="Green = the team is good at it. Stingy defenses are green." onClick={() => setView('strength')}>
            Team Strength View
          </button>
        </div>
      </div>

      <div className="cut-note tr-note-strip">
        SHOWING: {cutText} · {view === 'betting' ? 'BETTING VIEW' : 'TEAM STRENGTH VIEW'} · ON DEFENSE COLUMNS GREEN = {defWord.toUpperCase()}
      </div>

      <table className="tr-table2">
        <thead>
          <tr>
            <th className="num">#</th>
            <th className="team">TEAM</th>
            <th>GP</th>
            <th title="Market-implied expected goals tonight (vig removed; implied total split by the moneyline). Slate teams only.">xG TONIGHT</th>
            {COLS.map((c) => {
              const on = sort.key === c.key
              return (
                <th
                  key={c.key}
                  className={`sortable${on ? ' on' : ''}`}
                  aria-sort={on ? (sort.dir === 'desc' ? 'descending' : 'ascending') : 'none'}
                  title={`${c.what}. Click to sort; click again to reverse.`}
                  onClick={() => setSort({ key: c.key, dir: on ? (sort.dir === 'desc' ? 'asc' : 'desc') : greenEnd(c, view) })}
                >
                  <span className="h">
                    {c.label} {on && (sort.dir === 'desc' ? '↓' : '↑')}
                  </span>
                  {on && (
                    <>
                      <small>{sort.dir === 'desc' ? c.most : c.fewest}</small>
                      <i>{tagFor(c, sort.dir).toUpperCase()} FIRST</i>
                    </>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((x, i) => (
            <tr key={x.abbr} className={tonight.has(x.abbr) ? 'tonight' : ''}>
              <td className="num">
                <span>{i + 1}</span>
              </td>
              <td className="team">
                <img src={LOGO(x.abbr)} alt="" />
                {x.city} {x.name}
                {tonight.has(x.abbr) && <small>TONIGHT</small>}
              </td>
              <td>{x.r.gp ?? '—'}</td>
              <td className={`xgcol ${xg[x.abbr]?.tone ?? ''}`}>
                {xg[x.abbr] ? xg[x.abbr].v.toFixed(2) : ''}
                {xg[x.abbr] && <small>{xg[x.abbr].opp}</small>}
              </td>
              {COLS.map((c) => {
                const v = x.r[c.key]
                const rk = x.r[`${c.key}_rk`]
                const t: Tone = tone(c.key, x.r[`${c.key}_t`], rk, view)
                if (sort.key !== c.key) {
                  // quiet columns: only the outlier tiers carry color
                  return (
                    <td key={c.key} className={t === 'g2' || t === 'r2' ? `quiet ${t}` : 'quiet'} title={rk == null ? undefined : `${ordinal(rk)} of 32 (1st = most)`}>
                      {c.fmt(v)}
                    </td>
                  )
                }
                const w = v == null || sp.hi === sp.lo ? 0 : 8 + (92 * (v - sp.lo)) / (sp.hi - sp.lo)
                return (
                  <td key={c.key} className={`sorted ${t || 'n'}`}>
                    <span className="pill">{c.fmt(v)}</span>
                    <span className="bar">
                      <span style={{ width: `${w}%` }} />
                    </span>
                    <span className="ord">{rk == null ? '' : `#${rk}`}</span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tr-note">
        Rank #1 = the most of that number in every column, so on goals and shots allowed #1 is the leakiest team. Ranks and tiers are among all 32 teams for the selected window and venue, and don't change when you filter by conference or division.
        Five tiers by distance from the league average: strong green and strong red are the outliers (1.5+ standard deviations), soft green and soft red are clearly above or below (0.5 to 1.5), gray is average.
        Only the sorted column shows every tier; the other columns color the outliers only.
      </p>
    </div>
  )
}
