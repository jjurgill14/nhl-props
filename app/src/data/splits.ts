import type { Board, LeaderBlock, RateBlock, SplitSel, SplitVenue, SplitWindow, TeamResult, TeamSide } from './types'

export const DEFAULT_SPLIT: SplitSel = { window: 'season', venue: 'all', defense: 'opp' }

export const WINDOW_OPTS: { key: SplitWindow; label: string }[] = [
  { key: 'season', label: 'Season' },
  { key: 'l10', label: 'L10' },
  { key: 'l5', label: 'L5' },
]
export const VENUE_OPTS: { key: SplitVenue; label: string; title: string }[] = [
  { key: 'all', label: 'All', title: 'All games' },
  { key: 'home', label: 'Home', title: 'Home games only, both teams' },
  { key: 'away', label: 'Away', title: 'Away games only, both teams' },
  { key: 'tonight', label: 'Tonight', title: "Each team in tonight's venue: the away team's road games, the home team's home games" },
]

const venueFor = (venue: SplitVenue, side: 'away' | 'home') => (venue === 'tonight' ? side : venue)
export const cutKey = (sel: SplitSel, side: 'away' | 'home') => `${sel.window}|${venueFor(sel.venue, side)}`

/** Rates for a team under the current selection. Falls back to the season numbers on boards built before splits existed. */
export function ratesFor(board: Board, team: TeamSide, side: 'away' | 'home', sel: SplitSel): RateBlock | undefined {
  return board.splits?.teams[team.abbr]?.[cutKey(sel, side)] ?? team.rates
}

export function leadersFor(board: Board, abbr: string, side: 'away' | 'home', sel: SplitSel): LeaderBlock | undefined {
  return board.splits?.leaders[abbr]?.[cutKey(sel, side)]
}

/** "L5 · AWAY" style caption for whatever cut a team is showing. */
export function cutLabel(sel: SplitSel, side: 'away' | 'home'): string {
  const w = sel.window === 'season' ? 'SEASON' : sel.window.toUpperCase()
  const v = venueFor(sel.venue, side)
  return v === 'all' ? w : `${w} · ${v.toUpperCase()}`
}

const WINDOW_N: Record<SplitWindow, number | null> = { season: null, l10: 10, l5: 5 }

/** The games behind a team's current cut, newest first. `total` is how many games the cut holds. */
export function resultsFor(board: Board, abbr: string, side: 'away' | 'home', sel: SplitSel): { games: TeamResult[]; total: number } | undefined {
  const all = board.splits?.results?.[abbr]
  if (!all) return undefined
  const v = venueFor(sel.venue, side)
  const inVenue = v === 'all' ? all : all.filter((g) => g.home === (v === 'home'))
  const n = WINDOW_N[sel.window]
  const cut = n ? inVenue.slice(-n) : inVenue
  return { games: [...cut].reverse(), total: cut.length }
}

/** Season record in one venue, e.g. "9-5-0"; undefined on boards without splits. */
export function seasonRecord(board: Board, abbr: string, venue: 'all' | 'home' | 'away'): string | undefined {
  return board.splits?.teams[abbr]?.[`season|${venue}`]?.rec
}
