// Team badge ("puck"): the designer's artwork for the team, lettered at render time with the
// NHL New Jersey font. One template per team in docs/badges/<ABBR>.svg (artwork only; the root
// carries data-fill / data-stroke for the lettering). Placeholders are generated from a palette
// until the designer delivers the real one — same contract, so swapping is a file drop.
import { useEffect, useState } from 'react'
import { DATA_BASE } from '../data/load'

// Geometry from the designer's Boston file (viewBox 1034.96).
const VB = 1034.96
const CX = VB / 2
const NUM = { size: 291.08, base: 373.44, spacing: 0.03, stroke: 14 }
const NAME = { size: 131.39, base: 565.37, spacing: 0.07, stroke: 7, maxW: 905, min: 40 }

declare global {
  interface Window { __BADGES__?: Record<string, string>; __BADGE_WIDTHS__?: Record<string, number>; __BADGE_FONT__?: string }
}

const templates = new Map<string, Promise<string | null>>()
let widthsP: Promise<Record<string, number>> | null = null
let fontInjected = false

function ensureFont() {
  if (fontInjected || typeof document === 'undefined') return
  fontInjected = true
  const src = window.__BADGE_FONT__ ? `url(data:font/ttf;base64,${window.__BADGE_FONT__})` : `url(${DATA_BASE}fonts/NHLNewJersey.ttf)`
  const st = document.createElement('style')
  st.textContent = `@font-face{font-family:'NHL New Jersey';src:${src} format('truetype');font-display:swap}`
  document.head.appendChild(st)
}

function loadWidths(): Promise<Record<string, number>> {
  if (widthsP) return widthsP
  if (window.__BADGE_WIDTHS__) return (widthsP = Promise.resolve(window.__BADGE_WIDTHS__))
  return (widthsP = fetch(`${DATA_BASE}badges/widths.json`)
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({})))
}

export function loadTemplate(abbr: string): Promise<string | null> {
  let p = templates.get(abbr)
  if (p) return p
  if (window.__BADGES__) p = Promise.resolve(window.__BADGES__[abbr] ?? null)
  else
    p = fetch(`${DATA_BASE}badges/${abbr}.svg`)
      .then((r) => (r.ok ? r.text() : null))
      .catch(() => null)
  templates.set(abbr, p)
  return p
}

/** Fit the surname: shrink until it clears the hem clip width. Pure, so it is testable. */
export function fitName(name: string, widths: Record<string, number>): number {
  const em = (s: string, size: number) => {
    const adv = [...s].reduce((a, c) => a + (widths[c] ?? widths['?'] ?? 0.47), 0)
    return adv * size + NAME.spacing * size * (s.length - 1)
  }
  let size = NAME.size
  if (!Object.keys(widths).length) return name.length > 11 ? 82 : name.length > 9 ? 100 : NAME.size
  while (em(name, size) > NAME.maxW && size > NAME.min) size -= 2
  return size
}

export function surname(name: string): string {
  // "J.T. Miller" -> "MILLER"; "Nugent-Hopkins" stays hyphenated; strip accents the font lacks
  return name
    .split(' ')
    .slice(-1)[0]
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
}

function letter(template: string, name: string, number: string, size: number): string {
  const fill = /data-fill="([^"]+)"/.exec(template)?.[1] ?? '#fff'
  const stroke = /data-stroke="([^"]+)"/.exec(template)?.[1] ?? '#000'
  const g =
    `<g font-family="'NHL New Jersey',Impact,'Arial Narrow',sans-serif" text-anchor="middle" fill="${fill}" stroke="${stroke}" stroke-linejoin="round" paint-order="stroke">` +
    `<text x="${CX}" y="${NUM.base}" font-size="${NUM.size}" letter-spacing="${(NUM.spacing * NUM.size).toFixed(2)}" stroke-width="${NUM.stroke}">${number}</text>` +
    `<text x="${CX}" y="${NAME.base}" font-size="${size.toFixed(2)}" letter-spacing="${(NAME.spacing * size).toFixed(2)}" stroke-width="${NAME.stroke}">${name}</text>` +
    `</g>`
  // lettering sits under the inner ring: insert before the last <path (the ring)
  const i = template.lastIndexOf('<path')
  return i < 0 ? template.replace('</svg>', g + '</svg>') : template.slice(0, i) + g + template.slice(i)
}

interface Props {
  team: string
  name: string
  number: number | null | undefined
  size?: number
  dim?: boolean
  /** Rendered while the template loads or when the team has none. */
  fallback?: React.ReactNode
}

export function Badge({ team, name, number, size = 104, dim = false, fallback = null }: Props) {
  const [html, setHtml] = useState<string | null>(null)
  useEffect(() => {
    ensureFont()
    let live = true
    Promise.all([loadTemplate(team), loadWidths()]).then(([tpl, widths]) => {
      if (!live || !tpl) return
      const last = surname(name)
      setHtml(letter(tpl, last, number == null ? '' : String(number), fitName(last, widths)))
    })
    return () => {
      live = false
    }
  }, [team, name, number])
  if (!html) return <>{fallback}</>
  return (
    <span
      className="badge"
      role="img"
      aria-label={`${name} #${number ?? ''}`}
      style={{ display: 'inline-block', width: size, height: size, opacity: dim ? 0.45 : 1 }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
