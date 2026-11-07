import type { ReactNode } from 'react'

export type Route = 'slate' | 'matchup' | 'lineups' | 'changes' | 'props' | 'analysis'

const NAV: { key: Route; label: string; icon: ReactNode }[] = [
  {
    key: 'slate',
    label: 'Daily slate',
    icon: (
      <svg viewBox="0 0 24 24">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    key: 'lineups',
    label: 'Lines & lineups',
    icon: (
      <svg viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="7" />
        <path d="m16 16 5 5" />
      </svg>
    ),
  },
  {
    key: 'changes',
    label: 'Line changes',
    icon: (
      <svg viewBox="0 0 24 24">
        <path d="M4 17h5l3-5 3 3 5-9" />
        <path d="M16 6h4v4" />
      </svg>
    ),
  },
  {
    key: 'props',
    label: 'Player props',
    icon: (
      <svg viewBox="0 0 24 24">
        <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
      </svg>
    ),
  },
  {
    key: 'analysis',
    label: 'Betting analysis',
    icon: (
      <svg viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" />
      </svg>
    ),
  },
]

interface Props {
  route: Route
  onRoute: (r: Route) => void
  mode: 'live' | 'demo'
  statusLabel: string
  children: ReactNode
}

export function Shell({ route, onRoute, mode, statusLabel, children }: Props) {
  return (
    <div className="app">
      <aside className="rail" aria-label="Primary navigation">
        <div className="rail-logo" title="ICEBOARD">
          ✳
        </div>
        <div className="rail-sep" />
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`rail-btn${route === n.key ? ' active' : ''}`}
            aria-label={n.label}
            title={n.label}
            aria-current={route === n.key ? 'page' : undefined}
            onClick={() => onRoute(n.key)}
          >
            {n.icon}
          </button>
        ))}
        <div className="rail-foot">ICEBOARD</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="brand">
            <span className="wordmark">
              ICE<span>BOARD</span>
              <span style={{ fontSize: 11, color: '#829daf', letterSpacing: 0, marginLeft: 7 }}>/ NHL</span>
            </span>
            <span className="brand-divider" />
            <span className="brand-sub">PERSONAL BETTING INTELLIGENCE</span>
          </div>
          <div className="top-actions">
            <span className="data-label">
              <span className="live-dot" style={mode === 'live' ? { background: '#9de0b6', boxShadow: '0 0 0 4px #9de0b610' } : undefined} />
              {mode === 'live' ? 'LIVE DATA · MODEL PLAYS' : 'SNAPSHOT · NOT TONIGHT'}
            </span>
            <span className="top-sep" />
            <span className="status">{statusLabel}</span>
            <span className="profile">JJ</span>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
