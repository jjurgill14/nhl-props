import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { Board } from '../pages/Board'
import { MatchupPage } from '../pages/Matchup'
import { DEFAULT_SPLIT } from '../data/splits'
import type { Board as BoardData, Game, RateBlock, SplitSel, TeamSide } from '../data/types'

const team = (abbr: string, city: string, name: string): TeamSide => ({
  abbr, city, name, color: '#fff', color2: '#000', record: '5-5-0', b2b: false,
  goalie: 'G', goalie_status: 'Confirmed', goalie_news: null, goalie_source: null, sv: '.900', gaa: '3.00',
  lineup_as_of: null, lineup_stale: false, ga_rk: 10, gf_rk: 10, ppga_rk: 10,
})
const empty = { point: [], assist: [], goal: [], sneaky_point: [], sneaky_assist: [], sneaky_goal: [], pair: [], two: [], pp1: [], btts2: [] }
const game: Game = {
  id: '01', game_id: 1, start_utc: '2026-11-08T00:00:00Z', status: 'FUT', venue: 'Arena',
  away: team('MTL', 'Montreal', 'Canadiens'), home: team('TOR', 'Toronto', 'Maple Leafs'),
  markets: { moneyline: { away: '+120', home: '-140', provider: 'Daily Faceoff', as_of: null }, total: { line: null, provider: null, as_of: null } },
  lenses: empty,
}
// every cut gets its own GF rank so the test can tell which one is on screen
const block = (gf_rk: number, ga_rk: number, rec: string): RateBlock => ({ gp: 5, rec, gf: 3, gf_rk, ga: 3, ga_rk, sf: 30, sf_rk: 16, sa: 30, sa_rk: 16, pp: 20, pp_rk: 16, pk: 80, pk_rk: 16 })
const cuts = (base: number) => Object.fromEntries(
  ['season', 'l10', 'l5'].flatMap((w, i) => ['all', 'home', 'away'].map((v, j) => [`${w}|${v}`, block(base + i * 3 + j, base + 10 + i * 3 + j, `${i}-${j}-0`)])),
)
const leaders = (name: string) => Object.fromEntries(
  ['season', 'l10', 'l5'].flatMap((w) => ['all', 'home', 'away'].map((v) => [`${w}|${v}`, {
    p: [{ id: 7, name: `${name} ${w} ${v}`, pos: 'C', gp: 5, v: 9 }], g: [], a: [], sog: [],
  }])),
)
const board: BoardData = {
  mode: 'live', date: '2026-11-07', generated_utc: '2026-11-07T10:00:00Z',
  lenses: { point: 'Point', assist: 'Assist', goal: 'Goal', sneaky_point: 'SP', sneaky_assist: 'SA', sneaky_goal: 'SG', pair: 'Pair', two: '2+', pp1: 'PP1', btts2: 'BTTS' },
  default_slots: ['point', 'pair', 'two'], games: [game], sources: { moneyline: 'Daily Faceoff' },
  splits: {
    windows: ['season', 'l10', 'l5'], venues: ['all', 'home', 'away'], teams: { MTL: cuts(1), TOR: cuts(2) }, leaders: { MTL: leaders('Mtl'), TOR: leaders('Tor') },
    results: {
      MTL: [
        { date: '2026-10-01', game_id: 1, opp: 'BOS', home: true, tf: 4, ta: 2, ot: 'REG' },
        { date: '2026-10-03', game_id: 2, opp: 'NYR', home: false, tf: 2, ta: 3, ot: 'OT' },
        { date: '2026-10-05', game_id: 3, opp: 'OTT', home: false, tf: 5, ta: 1, ot: 'REG' },
      ],
      TOR: [],
    },
  },
}

function Harness({ onProps }: { onProps?: (t: unknown) => void }) {
  const [sel, setSel] = useState<SplitSel>(DEFAULT_SPLIT)
  return <MatchupPage board={board} gameId="01" onPick={() => {}} sel={sel} onSel={setSel} onBack={() => {}} onProps={onProps} />
}

describe('Matchup page', () => {
  it('shows each offense against the OPPONENT defense by default, and flips to own defense', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const mtl = screen.getByRole('region', { name: 'MTL SEASON' })
    expect(within(mtl).getByText('MTL OFFENSE')).toBeInTheDocument()
    expect(within(mtl).getByText('TOR DEFENSE')).toBeInTheDocument()
    expect(within(mtl).getByText('#12')).toBeInTheDocument() // TOR season|all ga_rk = 2 + 10
    await user.click(screen.getByRole('button', { name: 'Own' }))
    expect(within(mtl).getByText('MTL DEFENSE')).toBeInTheDocument()
    expect(within(mtl).getByText('#11')).toBeInTheDocument() // MTL season|all ga_rk = 1 + 10
  })

  it('window and venue toggles change the cut for rates, record and leaders', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'L5' }))
    await user.click(screen.getByRole('button', { name: 'Away' }))
    const mtl = screen.getByRole('region', { name: 'MTL L5 · AWAY' })
    expect(within(mtl).getByText('#9')).toBeInTheDocument() // MTL l5|away gf_rk = 1 + 2*3 + 2
    expect(within(mtl).getByText('5 GP · 2-2-0')).toBeInTheDocument()
    expect(within(mtl).getByText('Mtl l5 away')).toBeInTheDocument()
  })

  it("'Tonight' puts the away team on its road games and the home team on its home games", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Tonight' }))
    expect(screen.getByRole('region', { name: 'MTL SEASON · AWAY' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'TOR SEASON · HOME' })).toBeInTheDocument()
  })

  it('shows overall / home / away records and the games behind the cut, newest first', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const head = screen.getByRole('heading', { level: 2, name: /Montreal/ }).parentElement!.querySelector('.mu-rec') as HTMLElement
    expect(within(head).getByText('OVERALL').parentElement).toHaveTextContent('0-0-0') // season|all
    expect(within(head).getByText('HOME').parentElement).toHaveTextContent('0-1-0') // season|home
    expect(within(head).getByText('AWAY').parentElement).toHaveTextContent('0-2-0') // season|away
    const mtl = screen.getByRole('region', { name: 'MTL SEASON' })
    expect(within(mtl).getAllByText(/^[WL] \d+-\d+/).map((e) => e.textContent)).toEqual(['W 5-1', 'L 2-3 OT', 'W 4-2'])
    await user.click(screen.getByRole('button', { name: 'Home' }))
    expect(within(screen.getByRole('region', { name: 'MTL SEASON · HOME' })).getAllByText(/^[WL] \d+-\d+/).map((e) => e.textContent)).toEqual(['W 4-2'])
  })

  it('clicking a leader opens his props with the right stat', async () => {
    const user = userEvent.setup()
    const onProps = vi.fn()
    render(<Harness onProps={onProps} />)
    await user.click(screen.getByText('Mtl season all'))
    expect(onProps).toHaveBeenCalledWith({ players: [7], stat: 'p', line: 0.5 })
  })
})

describe('Board with split toggles', () => {
  it('card click opens the matchup page; the rank chips follow the toggles', async () => {
    const user = userEvent.setup()
    const onMatchup = vi.fn()
    function B() {
      const [sel, setSel] = useState<SplitSel>(DEFAULT_SPLIT)
      return <Board board={board} onMatchup={onMatchup} sel={sel} onSel={setSel} />
    }
    render(<B />)
    const card = screen.getByRole('button', { name: 'Open MTL at TOR matchup' })
    expect(within(card).getAllByText('#1').length).toBe(1) // MTL season GF rank
    await user.click(screen.getByRole('button', { name: 'L10' }))
    expect(within(card).queryByText('#1')).not.toBeInTheDocument()
    expect(within(card).getByText('#4')).toBeInTheDocument() // MTL l10|all gf_rk
    expect(within(card).getByText(/RANKS: L10/)).toBeInTheDocument()
    await user.click(card)
    expect(onMatchup).toHaveBeenCalledWith('01')
  })
})
