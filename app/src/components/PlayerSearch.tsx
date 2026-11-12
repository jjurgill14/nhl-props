import { useEffect, useMemo, useRef, useState } from 'react'
import { loadPlayerIndex, type PlayerIndexRow } from '../data/load'

interface Props {
  onPick: (id: number) => void
  placeholder?: string
  autoFocus?: boolean
}

/** Type-ahead over every skater who has dressed this season (any team). */
export function PlayerSearch({ onPick, placeholder = 'Search any player…', autoFocus }: Props) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<PlayerIndexRow[]>([])
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    loadPlayerIndex().then(setRows).catch(() => setRows([]))
  }, [])
  useEffect(() => {
    if (autoFocus) ref.current?.focus()
  }, [autoFocus])
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (t.length < 2) return []
    const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    return rows
      .filter((r) => norm(r.name).includes(norm(t)) || r.team.toLowerCase() === t)
      .sort((a, b) => b.gp - a.gp)
      .slice(0, 10)
  }, [q, rows])
  const pick = (r: PlayerIndexRow) => {
    onPick(r.id)
    setQ('')
    setOpen(false)
  }
  return (
    <div className="psearch">
      <label className="search" title="Search any player">
        <svg viewBox="0 0 24 24">
          <circle cx="10.5" cy="10.5" r="7" />
          <path d="m16 16 5 5" />
        </svg>
        <input
          ref={ref}
          type="search"
          aria-label="Search players"
          placeholder={placeholder}
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOpen(true)
            setHi(0)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') setHi((h) => Math.min(h + 1, hits.length - 1))
            else if (e.key === 'ArrowUp') setHi((h) => Math.max(h - 1, 0))
            else if (e.key === 'Enter' && hits[hi]) pick(hits[hi])
            else if (e.key === 'Escape') setOpen(false)
          }}
        />
      </label>
      {open && hits.length > 0 && (
        <ul className="psearch-list" role="listbox">
          {hits.map((r, i) => (
            <li key={r.id} role="option" aria-selected={i === hi} className={i === hi ? 'hi' : ''} onMouseDown={() => pick(r)}>
              <b>{r.name}</b>
              <span>
                {r.team} · {r.pos ?? '–'} · #{r.jersey ?? '–'} · {r.gp} GP
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
