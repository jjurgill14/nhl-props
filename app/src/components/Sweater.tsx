// Back-of-sweater graphic in team colors: name arched over the number. One component, 32 teams,
// any player — rendered from data, not artwork.

function luminance(hex: string): number {
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

interface Props {
  name: string
  number: number | null | undefined
  color: string
  color2: string
  size?: number
  dim?: boolean
}

export function Sweater({ name, number, color, color2, size = 120, dim = false }: Props) {
  const last = name.split(' ').slice(-1)[0].toUpperCase()
  const ink = luminance(color) > 0.45 ? '#0b1118' : '#ffffff'
  const trim = color2 === '#FFFFFF' || color2 === '#ffffff' ? '#e9eef3' : color2
  const nameSize = last.length > 11 ? 6.6 : last.length > 9 ? 7.6 : last.length > 7 ? 9 : last.length > 5 ? 10.5 : 12
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} role="img" aria-label={`${name} #${number ?? ''}`} style={{ opacity: dim ? 0.45 : 1 }}>
      <defs>
        <linearGradient id="sw-sheen" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity=".12" />
          <stop offset="1" stopColor="#000" stopOpacity=".18" />
        </linearGradient>
      </defs>
      {/* body + sleeves */}
      <path d="M38 16 L60 11 L82 16 L108 28 L116 52 L100 58 L96 50 L96 104 Q96 110 90 110 L30 110 Q24 110 24 104 L24 50 L20 58 L4 52 L12 28 Z" fill={color} />
      {/* shoulder yoke */}
      <path d="M38 16 L60 11 L82 16 L108 28 L104 40 L82 30 L60 26 L38 30 L16 40 L12 28 Z" fill={trim} opacity=".9" />
      {/* collar */}
      <path d="M48 14 Q60 22 72 14 L70 11 Q60 17 50 11 Z" fill={trim} />
      {/* sleeve stripes */}
      <path d="M112 40 L104 43 L108 52 L116 49 Z" fill={trim} />
      <path d="M8 40 L16 43 L12 52 L4 49 Z" fill={trim} />
      {/* hem stripe */}
      <rect x="24" y="98" width="72" height="5" fill={trim} />
      <path d="M38 16 L60 11 L82 16 L108 28 L116 52 L100 58 L96 50 L96 104 Q96 110 90 110 L30 110 Q24 110 24 104 L24 50 L20 58 L4 52 L12 28 Z" fill="url(#sw-sheen)" />
      {/* name */}
      <path id={`arc-${last}-${number}`} d="M26 46 Q60 32 94 46" fill="none" />
      <text fontFamily="Inter, Arial Narrow, Arial, sans-serif" fontWeight="800" fontSize={nameSize} fill={ink} letterSpacing=".6" textAnchor="middle">
        <textPath href={`#arc-${last}-${number}`} startOffset="50%">
          {last}
        </textPath>
      </text>
      {/* number */}
      <text x="60" y="88" fontFamily="Inter, Arial, sans-serif" fontWeight="900" fontSize={number != null && number >= 10 ? 40 : 44} fill={ink} textAnchor="middle" stroke={trim} strokeWidth="1.2" paintOrder="stroke">
        {number ?? ''}
      </text>
    </svg>
  )
}
