// One color rule for every team number in the app.
//
// The pipeline gives each number a TIER: how far the team sits from the league average, in that stat's own
// spread, among the teams ranked together (see analysis.rank_rates). +2 / -2 are the outliers.
// This file turns a tier into a color, and that depends on which way is "good":
//   betting view  (the default, and the only view on the board and the matchup page):
//                 green = good for an offensive bet. Offense: high is green. Defense: LEAKY is green.
//   strength view (Team Rankings only): green = the team is good at it. Defense: STINGY is green.
// No yellow: the average tier is neutral.

export type RateKey = 'gf' | 'sf' | 'pp' | 'ppg' | 'ga' | 'sa' | 'pk' | 'ppga'
export type ColorView = 'betting' | 'strength'
/** g2 strong green · g1 soft green · '' neutral · r1 soft red · r2 strong red */
export type Tone = 'g2' | 'g1' | '' | 'r1' | 'r2'

export const isDefense = (key: RateKey) => key === 'ga' || key === 'sa' || key === 'pk' || key === 'ppga'

/** +2..-2 where positive = green, for this stat in this view. */
export function goodness(key: RateKey, tier: number, view: ColorView = 'betting'): number {
  if (!isDefense(key)) return tier // offense: a higher number is green in both views
  const leaky = key === 'pk' ? -tier : tier // a LOW penalty kill % is the leaky one
  return view === 'betting' ? leaky : -leaky
}

export function tone(key: RateKey, tier: number | null | undefined, rk: number | null | undefined, view: ColorView = 'betting'): Tone {
  if (tier == null) return legacyTone(key, rk ?? null, view)
  const g = goodness(key, tier, view)
  return g >= 2 ? 'g2' : g === 1 ? 'g1' : g === 0 ? '' : g === -1 ? 'r1' : 'r2'
}

/** Boards built before tiers existed only carry ranks: top 8 soft green, bottom 8 soft red (rank 1 = most). */
function legacyTone(key: RateKey, rk: number | null, view: ColorView): Tone {
  if (rk == null) return ''
  const tier = rk <= 8 ? 1 : rk >= 25 ? -1 : 0
  const g = goodness(key, tier, view)
  return g > 0 ? 'g1' : g < 0 ? 'r1' : ''
}

// text color is the same bright green / red for both strengths; the outlier tiers add a filled background where there's room
export const TONE_COLOR: Record<Tone, string> = { g2: '#4ade80', g1: '#4ade80', '': '#9fb3c1', r1: '#f87171', r2: '#f87171' }
