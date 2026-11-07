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
  players?: (number | null)[]
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
  lineup?: GameLineup
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

// ---- Lines & Lineups ----
export interface LineupPlayer {
  name: string
  jersey: number | null
  pos: string | null
  slot: number | null
  player_id: number | null
  dfo_id: number | null
  gtd: boolean
  injury: string | null
  pp: number | null
  pk: number | null
  bias: string | null
  season: { gp: number; g: number; a: number; p: number; ppp: number; sog: number; toi_s: number } | null
  last5: { gp: number; g: number; a: number; p: number; ppp: number; sog: number; toi_s: number } | null
  l5_point_games: number
  gp: number
  move: { ev: number; pp: number; new: boolean }
  record?: string | null
  sv_pct?: string | null
  starts?: number
}

export interface TeamLineup {
  team: string
  as_of: string | null
  stale: boolean
  source: string
  updated_dfo: string | null
  forwards: LineupPlayer[][]
  defense: LineupPlayer[][]
  goalies: LineupPlayer[][]
  pp: LineupPlayer[][]
  pk: LineupPlayer[][]
  injuries: { player: string; status: string | null; news: string | null }[]
  unit_ratings: Record<string, { rank: number; rating: number }> | null
}

export interface GameLineup {
  away: TeamLineup | null
  home: TeamLineup | null
}

// ---- Player Props ----
export interface GameLogRow {
  date: string
  game_id: number
  opp: string
  home: boolean
  g: number
  a: number
  p: number
  sog: number
  pp_g: number
  toi_s: number
  pp_toi_s: number
}

export interface PlayerLog {
  id: number
  name: string
  team: string
  pos: string | null
  jersey: number | null
  log: GameLogRow[]
}

export type StatKey = 'g' | 'a' | 'p' | 'sog'
