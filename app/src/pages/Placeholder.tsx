import type { Route } from '../components/Shell'

const TITLES: Record<Route, [string, string]> = {
  slate: ['Daily slate', ''],
  matchup: ['Matchup details', 'Per-game breakdown — design pending.'],
  lineups: ['Lines & lineups', 'LW / C / RW grid, D pairs, PP units, goalies. Design approved; build is next.'],
  changes: ['Line changes', 'Promotions, demotions and new faces vs. the previous game day. Design pending.'],
  props: ['Player props', 'Design pending.'],
  rates: ['Team rates', ''],
  analysis: ['Betting analysis', 'Prediction log, grading, calibration. Design pending.'],
}

// Deliberately undesigned: these screens are being designed separately and arrive when approved.
export function Placeholder({ route }: { route: Route }) {
  const [title, note] = TITLES[route]
  return (
    <section className="hero" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
      <div className="eyebrow">NHL / {title.toUpperCase()}</div>
      <h1>{title}</h1>
      <p>{note}</p>
    </section>
  )
}
