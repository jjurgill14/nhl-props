import type { TeamRates } from '../data/types'

// Two rows per team. ONE color rule everywhere: green = good for an OFFENSIVE bet, red = bad.
//   SHOOTS   (GF, SF, PP) — this team's offense: green means bet THIS team's shooters.
//   GIVES UP (GA, SA, PK) — this team's defense, colored for the OPPONENT's shooters: a leaky
//            defense (rank near 1 = allows the most) is green, a wall is red.
// Rank convention stays "#1 = the most of that raw rate"; the colors do the translating.
type K = 'gf' | 'sf' | 'pp' | 'ga' | 'sa' | 'pk'
const OFF: { key: K; label: string; title: string }[] = [
  { key: 'gf', label: 'GF', title: 'Goals for / game (#1 = most)' },
  { key: 'sf', label: 'SF', title: 'Shots on goal / game (#1 = most)' },
  { key: 'pp', label: 'PP', title: 'Power play % (#1 = best)' },
]
const DEF: { key: K; label: string; title: string }[] = [
  { key: 'ga', label: 'GA', title: 'Goals allowed / game (#1 = allows most)' },
  { key: 'sa', label: 'SA', title: 'Shots allowed / game (#1 = allows most)' },
  { key: 'pk', label: 'PK', title: 'Penalty kill % (#1 = best kill)' },
]

/** tone for an offensive bet: offense chips good when rank is low; "gives up" chips good when the team is leaky. */
export function chipTone(key: K, rk: number | null): '' | 'hot' | 'cold' {
  if (rk == null) return ''
  const leakyIsGood = key === 'ga' || key === 'sa' // rank 1 = allows the most = good for the opponent's shooters
  const good = key === 'pk' ? rk >= 25 : leakyIsGood ? rk <= 8 : rk <= 8
  const bad = key === 'pk' ? rk <= 8 : leakyIsGood ? rk >= 25 : rk >= 25
  return good ? 'hot' : bad ? 'cold' : ''
}

function fmt(key: K, v: number | null | undefined): string {
  if (v == null) return '—'
  if (key === 'pp' || key === 'pk') return `${v}%`
  if (key === 'sf' || key === 'sa') return v.toFixed(1)
  return v.toFixed(2)
}

function Row({ cols, r, label, hint }: { cols: typeof OFF; r: TeamRates; label: string; hint: string }) {
  return (
    <div className="ranks" title={hint}>
      <span className="ranks-lbl">{label}</span>
      {cols.map((c) => {
        const rk = r[`${c.key}_rk`]
        return (
          <span key={c.key} className={`rk ${chipTone(c.key, rk)}`} title={`${c.title}: ${fmt(c.key, r[c.key])}`}>
            <i>{c.label}</i>
            <b>{rk == null ? '–' : `#${rk}`}</b>
          </span>
        )
      })}
    </div>
  )
}

export function RankStrip({ r, compact = false }: { r: TeamRates | undefined; compact?: boolean }) {
  if (!r) return null
  return (
    <div className={`ranks-wrap${compact ? ' compact' : ''}`}>
      <Row cols={OFF} r={r} label="SHOOTS" hint="This team's offense — green = bet this team's shooters" />
      <Row cols={DEF} r={r} label="GIVES UP" hint="This team's defense, colored for the OTHER team's shooters — green = they're leaky" />
    </div>
  )
}
