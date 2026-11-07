import type { Board, PlayerLog } from './types'

// The pipeline writes docs/board.json (today) and docs/boards/<date>.json (history).
// The app is served from docs/app/, so data is one level up.
// dev: Vite serves ../docs at the base URL; prod: the app lives in docs/app, data one level up
export const DATA_BASE = import.meta.env.DEV ? import.meta.env.BASE_URL : '../'

declare global {
  interface Window { __BOARD__?: Board; __LOGOS__?: Record<string, string>; __PLAYERS__?: Record<string, PlayerLog> }
}

export async function loadBoard(date?: string): Promise<Board> {
  // Standalone preview builds embed the board and logos directly in the HTML.
  if (!date && window.__BOARD__) return window.__BOARD__
  if (date && window.__BOARD__) throw new Error('snapshots are not embedded in the standalone preview')
  const url = date ? `${DATA_BASE}boards/${date}.json` : `${DATA_BASE}board.json`
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) throw new Error(`board ${date ?? 'today'}: HTTP ${res.status}`)
  const board = (await res.json()) as Board
  if (date) {
    board.mode = 'demo'
    board.snapshot_label = `Snapshot of ${date} · real data, not tonight`
  }
  return board
}

export const LOGO = (abbr: string) => window.__LOGOS__?.[abbr] ?? `${DATA_BASE}assets/logos/${abbr}_dark.svg`
export const MUG = (id: number | string) => `${DATA_BASE}assets/mugs/${id}.png`

export async function loadPlayer(id: number): Promise<PlayerLog> {
  const embedded = window.__PLAYERS__?.[String(id)]
  if (embedded) return embedded
  if (window.__BOARD__) throw new Error('player logs for this player are not embedded in the standalone preview')
  const res = await fetch(`${DATA_BASE}players/${id}.json`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`player ${id}: HTTP ${res.status}`)
  return (await res.json()) as PlayerLog
}
