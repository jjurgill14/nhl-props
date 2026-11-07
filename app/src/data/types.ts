// Data contract between the Python pipeline (docs/board.json) and the app.
// Nothing here is ever invented client-side: missing data stays null/empty.

export type LensKey = 'point' | 'pair' | 'two' | 'pp1' | 'btts2'

export interface Play {
  selection: string
  prob: number
  fair: string // American odds at our probability
  need: string // fair + edge margin: the worst price worth taking
  rationale: string
  player?: string
  team?: string
  pp?: number | null
  line?: number
  bias?: string | null
  read?: string
  both?: number
  n?: number
  verdict?: 'Yes' | 'No' | 'Maybe'
}

export interface TeamSide {
  abbr: string
  city: string
  name: string
  color: string
  color2: string
  record: string
  b2b: boolean
  goalie: string | null
  goalie_status: string | null
  goalie_news: string | null
  goalie_source: string | null
  sv: string | null
  gaa: string | null
  lineup_as_of: string | null
  lineup_stale: boolean
  ga_rk: number | null
  gf_rk: number | null
  ppga_rk: number | null
}

export interface Markets {
  moneyline: { away: string | null; home: string | null; provider: string | null; as_of: string | null }
  total: { line: number | null; provider: string | null; as_of: string | null }
}

export interface Game {
  id: string
  game_id: number
  start_utc: string
  status: string | null
  venue: string
  away: TeamSide
  home: TeamSide
  markets: Markets
  lenses: Record<LensKey, Play[]>
}

export interface Board {
  mode: 'live' | 'demo'
  date: string
  generated_utc: string
  lenses: Record<LensKey, string>
  default_slots: LensKey[]
  games: Game[]
  sources: Record<string, string>
  /** Set by the app when a board is loaded as a labeled historical snapshot. */
  snapshot_label?: string
}

export type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; board: Board }
