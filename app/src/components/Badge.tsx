// Team badge ("puck"): the designer's artwork for the team, lettered at render time with the
// NHL New Jersey font. One template per team in docs/badges/<ABBR>.svg (artwork only; the root
// carries data-fill / data-stroke for the lettering). Placeholders are generated from a palette
// until the designer delivers the real one — same contract, so swapping is a file drop.
import { useEffect, useState } from 'react'
import { DATA_BASE } from '../data/load'

// Geometry from the designer's Boston file (viewBox 1034.96).
const VB = 1034.96
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

/** Lettering geometry: the designer's file carries its own (data-* on the root); placeholders use Boston's. */
interface Spec { vb: number; numSize: number; numBase: number; numFill: string; numSpacing: number; nameSize: number; nameBase: number; nameFill: string; nameSpacing: number; nameMaxW: number; stroke: string; numStroke: number; nameStroke: number }
export function specOf(template: string): Spec {
  const attr = (k: string) => new RegExp(`\\sdata-${k}="([^"]*)"`).exec(template)?.[1]
  const num = (k: string, d: number) => { const v = attr(k); return v == null || v === '' ? d : Number(v) }
  const vb = num('vb', VB)
  const k = vb / VB
  const fill = attr('fill') ?? '#fff'
  return {
    vb,
    numSize: num('num-size', NUM.size * k), numBase: num('num-base', NUM.base * k), numFill: attr('num-fill') ?? fill, numSpacing: num('num-spacing', NUM.spacing),
    nameSize: num('name-size', NAME.size * k), nameBase: num('name-base', NAME.base * k), nameFill: attr('name-fill') ?? fill, nameSpacing: num('name-spacing', NAME.spacing),
    nameMaxW: num('name-maxw', NAME.maxW * k),
    stroke: attr('stroke') ?? '#000', numStroke: NUM.stroke * k, nameStroke: NAME.stroke * k,
  }
}

/** Fit the surname: shrink until it clears the hem clip width. Pure, so it is testable. */
export function fitName(name: string, widths: Record<string, number>, spec?: Pick<Spec, 'nameSize' | 'nameSpacing' | 'nameMaxW'>): number {
  const size0 = spec?.nameSize ?? NAME.size
  const spacing = spec?.nameSpacing ?? NAME.spacing
  const maxW = spec?.nameMaxW ?? NAME.maxW
  const em = (s: string, size: number) => {
    const adv = [...s].reduce((a, c) => a + (widths[c] ?? widths['?'] ?? 0.47), 0)
    return adv * size + spacing * size * (s.length - 1)
  }
  let size = size0
  if (!Object.keys(widths).length) return name.length > 11 ? size0 * 0.62 : name.length > 9 ? size0 * 0.76 : size0
  const min = size0 * 0.3
  while (em(name, size) > maxW && size > min) size -= size0 / 65
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

function letter(template: string, name: string, number: string, size: number, sp: Spec): string {
  const cx = sp.vb / 2
  const strokeAttrs = sp.stroke === 'none' ? '' : ` stroke="${sp.stroke}" stroke-linejoin="round" paint-order="stroke"`
  const g =
    `<g font-family="'NHL New Jersey',Impact,'Arial Narrow',sans-serif" text-anchor="middle"${strokeAttrs}>` +
    `<text x="${cx}" y="${sp.numBase}" fill="${sp.numFill}" font-size="${sp.numSize}" letter-spacing="${(sp.numSpacing * sp.numSize).toFixed(2)}" stroke-width="${sp.numStroke}">${number}</text>` +
    `<text x="${cx}" y="${sp.nameBase}" fill="${sp.nameFill}" font-size="${size.toFixed(2)}" letter-spacing="${(sp.nameSpacing * size).toFixed(2)}" stroke-width="${sp.nameStroke}">${name}</text>` +
    `</g>`
  // the build step marks where the lettering goes (just under the inner ring); fall back to before the last path
  const marker = /<g id="[A-Z]{3}-lettering"><\/g>/.exec(template)
  if (marker) return template.slice(0, marker.index) + g + template.slice(marker.index + marker[0].length)
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
      const sp = specOf(tpl)
      setHtml(letter(tpl, last, number == null ? '' : String(number), fitName(last, widths, sp), sp))
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
