import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Board } from '../pages/Board'
import { etBucket, etTime } from '../data/time'
import type { Board as BoardData, Game, TeamSide } from '../data/types'

const team = (abbr: string, city: string, name: string): TeamSide => ({
  abbr, city, name, color: '#fff', color2: '#000', record: '5-5-0', b2b: false,
  goalie: 'G', goalie_status: 'Confirmed', goalie_news: null, goalie_source: null, sv: '.900', gaa: '3.00',
  lineup_as_of: '2026-11-07T20:00:00Z', lineup_stale: false, ga_rk: 10, gf_rk: 10, ppga_rk: 10,
})

const game = (id: string, start_utc: string, away: TeamSide, home: TeamSide, plays = true): Game => ({
  id, game_id: Number(id), start_utc, status: 'FUT', venue: 'Arena', away, home,
  markets: { moneyline: { away: '+120', home: '-140', provider: 'Daily Faceoff', as_of: null }, total: { line: null, provider: null, as_of: null } },
  lenses: {
    point: plays ? [{ selection: `${away.abbr} guy · 1+ point`, prob: 0.6, fair: '-150', need: '-130', rationale: 'because' }] : [],
    pair: [], two: [], pp1: [], btts2: [],
  },
})

// Nov 7 2026 is EST (DST ended Nov 1): 17:30Z = 12:30 PM ET, 00:00Z next day = 7:00 PM ET.
const fixture: BoardData = {
  mode: 'live', date: '2026-11-07', generated_utc: '2026-11-07T10:00:00Z',
  lenses: { point: 'Point', pair: 'Pair', two: '2+ points', pp1: 'PP1 mates', btts2: 'Both teams 2+' },
  default_slots: ['point', 'pair', 'two'],
  games: [
    game('01', '2026-11-07T17:30:00Z', team('FLA', 'Florida', 'Panthers'), team('WSH', 'Washington', 'Capitals')),
    game('02', '2026-11-08T00:00:00Z', team('MTL', 'Montreal', 'Canadiens'), team('TOR', 'Toronto', 'Maple Leafs')),
    game('03', '2026-11-08T00:30:00Z', team('NJD', 'New Jersey', 'Devils'), team('NYI', 'New York', 'Islanders'), false),
  ],
  sources: { moneyline: 'Daily Faceoff' },
}

describe('Eastern Time handling', () => {
  it('formats and buckets in America/New_York with DST handled', () => {
    expect(etTime('2026-11-07T17:30:00Z')).toBe('12:30 PM') // EST
    expect(etTime('2026-10-07T23:00:00Z')).toBe('7:00 PM') // EDT
    expect(etBucket('2026-11-08T00:30:00Z')).toBe('7:30')
    expect(etBucket('2026-11-08T00:00:00Z')).toBe('7')
  })
})

describe('The Board', () => {
  it('renders every game with three equal play slots', () => {
    render(<Board board={fixture} />)
    expect(screen.getByTestId('matchup-count')).toHaveTextContent('3 MATCHUPS')
    expect(screen.getAllByRole('button', { name: /Open .* breakdown/ })).toHaveLength(3)
    expect(screen.getAllByText('OPEN BREAKDOWN ↗')).toHaveLength(3)
    expect(screen.getAllByText('No verified play yet').length).toBeGreaterThan(0)
  })

  it('filters by puck-drop chip including half-hour starts', async () => {
    const user = userEvent.setup()
    render(<Board board={fixture} />)
    await user.click(screen.getByRole('button', { name: '7:30' }))
    expect(screen.getByTestId('matchup-count')).toHaveTextContent('1 MATCHUP')
    expect(screen.getByText('New Jersey')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^All/ }))
    expect(screen.getByTestId('matchup-count')).toHaveTextContent('3 MATCHUPS')
  })

  it('team search narrows without breaking the time filter', async () => {
    const user = userEvent.setup()
    render(<Board board={fixture} />)
    await user.click(screen.getByRole('button', { name: '7' }))
    await user.type(screen.getByLabelText('Search teams'), 'toronto')
    expect(screen.getByTestId('matchup-count')).toHaveTextContent('1 MATCHUP')
    await user.clear(screen.getByLabelText('Search teams'))
    await user.type(screen.getByLabelText('Search teams'), 'florida')
    expect(screen.getByTestId('matchup-count')).toHaveTextContent('0 MATCHUPS') // Florida plays at 12:30, not 7
  })

  it('switches between Cards and List', async () => {
    const user = userEvent.setup()
    render(<Board board={fixture} />)
    await user.click(screen.getByTitle('Compact list layout'))
    expect(screen.getByText('PUCK DROP')).toBeInTheDocument()
    expect(screen.getByTitle('Compact list layout')).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByTitle('Card layout'))
    expect(screen.queryByText('PUCK DROP')).not.toBeInTheDocument()
  })

  it('opens the breakdown drawer for the clicked matchup and closes on Escape', async () => {
    const user = userEvent.setup()
    render(<Board board={fixture} />)
    await user.click(screen.getAllByRole('button', { name: /Open MTL at TOR breakdown/ })[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { level: 2 })).toHaveTextContent('Toronto Maple Leafs')
    expect(within(dialog).getByText('unavailable')).toBeInTheDocument() // no total feed → no invented number
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('lets a play slot be swapped for another lens', async () => {
    const user = userEvent.setup()
    render(<Board board={fixture} />)
    await user.selectOptions(screen.getByLabelText('Play slot 1'), 'two')
    // slot 3 is already '2+ points', so slots 1 and 3 both show the empty 2+ lens on all three games
    expect(screen.getAllByText(/2\+ points: nothing clears the bar/).length).toBe(6)
    expect(screen.queryByText(/FLA guy · 1\+ point/)).not.toBeInTheDocument()
  })

  it('labels a snapshot board as not tonight', () => {
    render(<Board board={{ ...fixture, mode: 'demo', snapshot_label: 'Snapshot of 2026-11-06 · real data, not tonight' }} />)
    expect(screen.getByText(/real data, not tonight/)).toBeInTheDocument()
    expect(screen.getByText(/ICEBOARD \/ SNAPSHOT/)).toBeInTheDocument()
  })
})
