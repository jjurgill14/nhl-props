import type { TeamRates } from '../data/types'

// Six ranks on one line. Convention: 1 = most. Colors are team quality: green = strong (top-8), red = weak (bottom-8).
// For GA/SA, rank 1 = allows the most, so a LOW rank there is weak (red) — a red opponent is what a prop bettor wants.
const COLS: { key: 'gf' | 'ga' | 'sf' | 'sa' | 'pp' | 'pk'; label: string; title: string; goodIsLow: boolean }[] = [
  { key: 'gf', label: 'GF', title: 'Goals for / game (rank 1 = most)', goodIsLow: true },
  { key: 'ga', label: 'GA', title: 'Goals allowed / game (rank 1 = allows most)', goodIsLow: false },
  { key: 'sf', label: 'SF', title: 'Shots on goal / game (rank 1 = most)', goodIsLow: true },
  { key: 'sa', label: 'SA', title: 'Shots allowed / game (rank 1 = allows most)', goodIsLow: false },
  { key: 'pp', label: 'PP', title: 'Power play % (rank 1 = best)', goodIsLow: true },
  { key: 'pk', label: 'PK', title: 'Penalty kill % (rank 1 = best)', goodIsLow: true },
]

function tone(rk: number | null, goodIsLow: boolean): string {
  if (rk == null) return ''
  const hot = goodIsLow ? rk <= 8 : rk >= 25
  const cold = goodIsLow ? rk >= 25 : rk <= 8
  return hot ? 'hot' : cold ? 'cold' : ''
}

export function RankStrip({ r, compact = false }: { r: TeamRates | undefined; compact?: boolean }) {
  if (!r) return null
  return (
    <div className={`ranks${compact ? ' compact' : ''}`}>
      {COLS.map((c) => {
        const rk = r[`${c.key}_rk`]
        const val = r[c.key]
        const txt = val == null ? '—' : c.key === 'pp' || c.key === 'pk' ? `${val}%` : c.key === 'sf' || c.key === 'sa' ? val.toFixed(1) : val.toFixed(2)
        return (
          <span key={c.key} className={`rk ${tone(rk, c.goodIsLow)}`} title={`${c.title}: ${txt}`}>
            <i>{c.label}</i>
            <b>{rk == null ? '–' : `#${rk}`}</b>
          </span>
        )
      })}
    </div>
  )
}
