import type { Board } from './types'

// The pipeline writes docs/board.json (today) and docs/boards/<date>.json (history).
// The app is served from docs/app/, so data is one level up.
// dev: Vite serves ../docs at the base URL; prod: the app lives in docs/app, data one level up
export const DATA_BASE = import.meta.env.DEV ? import.meta.env.BASE_URL : '../'

export async function loadBoard(date?: string): Promise<Board> {
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

export const LOGO = (abbr: string) => `${DATA_BASE}assets/logos/${abbr}_dark.svg`
export const MUG = (id: number | string) => `${DATA_BASE}assets/mugs/${id}.png`
