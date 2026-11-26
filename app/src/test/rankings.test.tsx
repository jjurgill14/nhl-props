import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TeamRatesPage } from '../pages/TeamRates'
import { tone } from '../data/tiers'
import type { Board, RateBlock } from '../data/types'

describe('tier colors', () => {
  it('offense: far above average is strong green in both views', () => {
    expect(tone('gf', 2, 1)).toBe('g2')
    expect(tone('gf', 2, 1, 'strength')).toBe('g2')
    expect(tone('pp', -1, 28)).toBe('r1')
    expect(tone('sf', 0, 15)).toBe('')
  })
  it('defense flips between views: leaky is green for betting, stingy is green for team strength', () => {
    expect(tone('ga', 2, 1, 'betting')).toBe('g2')
    expect(tone('ga', 2, 1, 'strength')).toBe('r2')
    expect(tone('sa', -2, 32, 'betting')).toBe('r2')
    expect(tone('sa', -2, 32, 'strength')).toBe('g2')
  })
  it('penalty kill: a LOW kill % is the leaky one', () => {
    expect(tone('pk', -2, 32, 'betting')).toBe('g2')
    expect(tone('pk', -2, 32, 'strength')).toBe('r2')
    expect(tone('pk', 1, 5, 'betting')).toBe('r1')
  })
  it('boards without tiers fall back to top 8 / bottom 8, never yellow', () => {
    expect(tone('gf', undefined, 3)).toBe('g1')
    expect(tone('gf', undefined, 15)).toBe('')
    expect(tone('ga', undefined, 30)).toBe('r1')
  })
})

const blk = (ga: number, ga_rk: number, ga_t: number, gf: number): RateBlock => ({
  gp: 20, rec: '10-8-2', gf, gf_rk: 5, gf_t: 0, ga, ga_rk, ga_t, sf: 28, sf_rk: 10, sf_t: 0, sa: 28, sa_rk: 10, sa_t: 0, pp: 20, pp_rk: 10, pp_t: 0, pk: 80, pk_rk: 10, pk_t: 0,
})
const TEAMS: Record<string, RateBlock> = { VAN: blk(4.41, 1, 2, 2.7), TOR: blk(3.2, 2, 0, 3.1), BOS: blk(2.41, 3, -2, 3.4) }
const cuts = (b: RateBlock) => Object.fromEntries(['season', 'l10', 'l5'].flatMap((w) => ['all', 'home', 'away'].map((v) => [`${w}|${v}`, b])))
const board = {
  mode: 'live', date: '2026-11-27', generated_utc: '2026-11-27T10:00:00Z', lenses: {}, default_slots: [], games: [], sources: {},
  team_rates: Object.fromEntries(Object.entries(TEAMS).map(([a, b]) => [a, { ...b, city: a, name: 'Team', color: '#fff', color2: '#000' }])),
  splits: { windows: [], venues: [], teams: Object.fromEntries(Object.entries(TEAMS).map(([a, b]) => [a, cuts(b)])), leaders: {} },
} as unknown as Board

describe('Team Rankings page', () => {
  it('opens in betting view sorted leakiest-first, with every tier in the sorted column only', () => {
    render(<TeamRatesPage board={board} />)
    expect(screen.getByRole('button', { name: 'Betting View' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('(Leakiest)')).toBeInTheDocument()
    expect(screen.getByText('LEAKIEST FIRST')).toBeInTheDocument()
    const body = screen.getAllByRole('row').slice(1)
    expect(within(body[0]).getByText(/VAN Team/)).toBeInTheDocument()
    expect(within(body[0]).getByText('4.41').closest('td')).toHaveClass('sorted', 'g2') // leaky outlier = strong green
    expect(within(body[2]).getByText('2.41').closest('td')).toHaveClass('sorted', 'r2')
    expect(within(body[1]).getByText('3.20').closest('td')).toHaveClass('sorted', 'n') // average = neutral
    expect(within(body[0]).getByText('2.70').closest('td')).toHaveClass('quiet') // other columns stay quiet
  })

  it('Team Strength view swaps defense colors and labels but not the order', async () => {
    const user = userEvent.setup()
    render(<TeamRatesPage board={board} />)
    await user.click(screen.getByRole('button', { name: 'Team Strength View' }))
    expect(screen.getByText('(Stingiest)')).toBeInTheDocument()
    expect(screen.getByText(/TEAM STRENGTH VIEW · ON DEFENSE COLUMNS GREEN = STINGY/)).toBeInTheDocument()
    const body = screen.getAllByRole('row').slice(1)
    expect(within(body[0]).getByText(/VAN Team/)).toBeInTheDocument() // same order
    expect(within(body[0]).getByText('4.41').closest('td')).toHaveClass('r2')
    expect(within(body[2]).getByText('2.41').closest('td')).toHaveClass('g2')
  })

  it('xG tonight sorts both ways, with teams not on the slate kept at the bottom', async () => {
    const user = userEvent.setup()
    const mk = (xa: number, xh: number) => ({ xg_away: xa, xg_home: xh, xg_tone_away: 'bad', xg_tone_home: 'good' })
    const withGame = { ...board, games: [{ id: '01', away: { abbr: 'VAN' }, home: { abbr: 'BOS' }, market: mk(2.5, 3.6) }] } as unknown as Board
    render(<TeamRatesPage board={withGame} />)
    const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).getByText(/Team/).textContent!.slice(0, 3))
    await user.click(screen.getByRole('columnheader', { name: /xG TONIGHT/ }))
    expect(names()).toEqual(['BOS', 'VAN', 'TOR']) // 3.60, 2.50, then TOR (not playing)
    expect(screen.getByText('HIGHEST FIRST')).toBeInTheDocument()
    await user.click(screen.getByRole('columnheader', { name: /xG TONIGHT/ }))
    expect(names()).toEqual(['VAN', 'BOS', 'TOR'])
    expect(screen.getByText('LOWEST FIRST')).toBeInTheDocument()
  })

  it('clicking the sorted header reverses it; clicking a card sorts by that column', async () => {
    const user = userEvent.setup()
    render(<TeamRatesPage board={board} />)
    await user.click(screen.getByRole('columnheader', { name: /GA\/G/ }))
    expect(screen.getByText('STINGIEST FIRST')).toBeInTheDocument()
    expect(within(screen.getAllByRole('row')[1]).getByText(/BOS Team/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Top 5 – GF\/G/ }))
    expect(screen.getByText('HIGHEST SCORING FIRST')).toBeInTheDocument()
    expect(within(screen.getAllByRole('row')[1]).getByText(/BOS Team/)).toBeInTheDocument() // 3.40 goals for
  })
})
