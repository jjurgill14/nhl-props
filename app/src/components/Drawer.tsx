import { useEffect, useRef } from 'react'
import type { Game, LensKey, TeamSide } from '../data/types'
import { LOGO } from '../data/load'
import { etStamp, etTime } from '../data/time'
import { propsFor, type PropsOpener } from './GameCard'

function TeamBlock({ t, side }: { t: TeamSide; side: 'AWAY' | 'HOME' }) {
  return (
    <div className="drawer-team">
      <img src={LOGO(t.abbr)} alt="" />
      <div>
        <b>
          {t.city} {t.name}
        </b>
        <small>
          {side} · {t.record} · GF #{t.gf_rk ?? '–'} · GA #{t.ga_rk ?? '–'} · PK #{t.ppga_rk ?? '–'}
          {t.b2b ? ' · back-to-back' : ''}
        </small>
        <small>
          🥅 {t.goalie ?? 'TBD'} ({t.goalie_status ?? 'unconfirmed'}) · {t.sv ?? '–'} sv% · {t.gaa ?? '–'} GAA
          {t.goalie_news ? ` — ${t.goalie_news}` : ''}
        </small>
        <small>lineup as of {etStamp(t.lineup_as_of)} ET</small>
      </div>
    </div>
  )
}

interface Props {
  game: Game | null
  lensLabels: Record<LensKey, string>
  onClose: () => void
  onLineups?: (id: string) => void
  onProps?: PropsOpener
}

export function Drawer({ game, lensLabels, onClose, onLineups, onProps }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!game) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [game, onClose])

  if (!game) return null
  const { away, home, markets } = game
  const order: LensKey[] = ['point', 'pair', 'two', 'pp1', 'btts2']
  return (
    <div className="overlay show" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <button ref={closeRef} className="close" aria-label="Close breakdown" onClick={onClose}>
          ×
        </button>
        <div className="kicker">
          MATCHUP {game.id} / {etTime(game.start_utc)} ET · {game.venue}
        </div>
        <h2 id="drawer-title">
          {away.city} {away.name}
          <br />
          <span style={{ color: '#6e94a6' }}>at</span> {home.city} {home.name}
        </h2>
        {onLineups && (
          <button type="button" className="future" style={{ width: '100%', cursor: 'pointer', color: '#c2dce5' }} onClick={() => { onLineups(game.id); onClose() }}>
            Lines & lineups for this game <span>OPEN ↗</span>
          </button>
        )}
        <TeamBlock t={away} side="AWAY" />
        <TeamBlock t={home} side="HOME" />
        <div className="drawer-stats">
          <div className="drawer-stat">
            <small>{away.abbr} MONEYLINE</small>
            <strong>{markets.moneyline.away ?? '—'}</strong>
          </div>
          <div className="drawer-stat">
            <small>GAME TOTAL</small>
            <strong style={{ color: '#f1c587', fontSize: markets.total.line == null ? 12 : undefined }}>
              {markets.total.line ?? 'unavailable'}
            </strong>
          </div>
          <div className="drawer-stat">
            <small>{home.abbr} MONEYLINE</small>
            <strong style={{ color: '#8ce2dc' }}>{markets.moneyline.home ?? '—'}</strong>
          </div>
        </div>
        {order.map((lens) => {
          const plays = game.lenses[lens] ?? []
          return (
            <section key={lens}>
              <h3>{lensLabels[lens].toUpperCase()}</h3>
              {plays.length === 0 && <div className="future">No verified play yet</div>}
              {plays.slice(0, 4).map((p, i) => {
                const t = onProps ? propsFor(p, lens) : null
                return (
                <div className={`drawer-play${t ? ' pr-link' : ''}`} key={i} title={t ? 'Open player props' : undefined} onClick={t ? () => { onProps!(t); onClose() } : undefined}>
                  <div className="head">
                    <b>
                      0{i + 1} · {p.selection}
                    </b>
                    <strong>{p.fair}</strong>
                  </div>
                  <p>
                    <span className="need">need {p.need} or better · our {Math.round(p.prob * 100)}%</span>
                    <br />
                    {p.rationale}
                  </p>
                </div>
                )
              })}
            </section>
          )
        })}
        <div className="drawer-warning">
          Prices are OUR fair odds from this season's data only (lineup as of {etStamp(home.lineup_as_of)} ET), not a
          sportsbook quote. "Need" is the worst price worth taking at a 6% edge. Moneylines: {markets.moneyline.provider}.
          Game totals arrive with the odds feed.
        </div>
      </div>
    </div>
  )
}
