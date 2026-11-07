import { useState } from 'react'
import type { Board, Game, LineupPlayer, TeamLineup, TeamSide } from '../data/types'
import { LOGO } from '../data/load'
import { etStamp, etTime } from '../data/time'
import { Sweater } from '../components/Sweater'

function Tag({ p }: { p: LineupPlayer }) {
  return (
    <span className="lu-tags">
      {p.pp === 1 && <i className="lu-tag pp1">PP1</i>}
      {p.pp === 2 && <i className="lu-tag pp2">PP2</i>}
      {p.pk === 1 && <i className="lu-tag pk">PK1</i>}
      {p.bias === 'G' && <i className="lu-tag g">G</i>}
      {p.bias === 'A' && <i className="lu-tag a">A</i>}
      {p.move.new && <i className="lu-tag new">NEW</i>}
      {!p.move.new && p.move.ev < 0 && <i className="lu-tag up">▲</i>}
      {!p.move.new && p.move.ev > 0 && <i className="lu-tag down">▼</i>}
      {p.gtd && <i className="lu-tag gtd">GTD</i>}
    </span>
  )
}

function PlayerCell({ p, team, size = 104 }: { p: LineupPlayer; team: TeamSide; size?: number }) {
  const s = p.season
  return (
    <div className="lu-player" title={s ? `${s.gp} GP · ${s.g}G ${s.a}A ${s.p}P · ${s.sog} SOG` : undefined}>
      <Sweater name={p.name} number={p.jersey} color={team.color} color2={team.color2} size={size} dim={p.gtd} />
      <div className="lu-name">
        {p.name} <span className="lu-pos">({p.pos ?? '–'})</span>
      </div>
      <div className="lu-stat">
        {s && s.gp != null ? `${s.p ?? 0} P in ${s.gp} GP · L5 ${p.l5_point_games}/${Math.min(5, p.gp)}` : p.gp ? `L5 ${p.l5_point_games}/${Math.min(5, p.gp)}` : 'no games yet'}
      </div>
      <Tag p={p} />
    </div>
  )
}

function Goalie({ p, team, label }: { p: LineupPlayer; team: TeamSide; label: string }) {
  return (
    <div className="lu-goalie">
      <Sweater name={p.name} number={p.jersey} color={team.color} color2={team.color2} size={92} />
      <div>
        <div className="lu-gname">
          <i className="lu-tag g-badge">G</i> {p.name}
        </div>
        <div className="lu-stat">({label})</div>
        <div className="lu-stat">
          {p.record ?? '0-0-0'} · {p.sv_pct ?? '–'} SV%
        </div>
      </div>
    </div>
  )
}

function TeamPanel({ lu, team, side, goalieStatus }: { lu: TeamLineup | null; team: TeamSide; side: 'AWAY' | 'HOME'; goalieStatus: string | null }) {
  if (!lu) {
    return (
      <section className="lu-panel">
        <div className="state-box">No lineup captured yet for {team.abbr}.</div>
      </section>
    )
  }
  const out = lu.injuries.filter((i) => i.status && i.status !== 'GTD')
  return (
    <section className="lu-panel" style={{ ['--team-accent' as string]: team.color }}>
      <header className="lu-head">
        <img src={LOGO(team.abbr)} alt="" />
        <div>
          <h3>
            {team.city} {team.name}
          </h3>
          <div className="lu-sub">
            {side} <span className="sep">|</span> Record: {team.record} <span className="sep">|</span>{' '}
            {lu.stale ? <b className="warn">last known lineup</b> : 'lineup'} as of {etStamp(lu.as_of)} ET
            {team.b2b && <i className="lu-tag b2b">B2B</i>}
          </div>
        </div>
      </header>

      <div className="lu-cols">
        <span />
        <span>LW</span>
        <span>C</span>
        <span>RW</span>
      </div>
      {lu.forwards.map((line, i) => (
        <div className="lu-line" key={i}>
          <div className="lu-label">Line {i + 1}</div>
          {line.map((p) => (
            <PlayerCell key={p.name} p={p} team={team} />
          ))}
        </div>
      ))}

      <div className="lu-bottom">
        <div className="lu-block">
          <h4>Defense Pairs</h4>
          {lu.defense.map((pair, i) => (
            <div className="lu-pair" key={i}>
              <div className="lu-label">D{i + 1}</div>
              {pair.map((p) => (
                <PlayerCell key={p.name} p={p} team={team} size={84} />
              ))}
            </div>
          ))}
        </div>
        <div className="lu-block">
          <h4>Goalies</h4>
          {lu.goalies[0]?.map((p) => (
            <Goalie key={p.name} p={p} team={team} label={goalieStatus ?? 'Projected'} />
          ))}
          {lu.goalies[1]?.map((p) => (
            <Goalie key={p.name} p={p} team={team} label="Backup" />
          ))}
          <h4 style={{ marginTop: 16 }}>Power play</h4>
          {lu.pp.map((u, i) => (
            <div className="lu-unit" key={i}>
              <b>PP{i + 1}</b> {u.map((p) => `${p.name.split(' ').slice(-1)[0]} ${p.jersey ?? ''}`).join(' · ')}
              {lu.unit_ratings?.[`pp${i + 1}`]?.rank ? <span className="muted"> · #{lu.unit_ratings[`pp${i + 1}`].rank} DFO</span> : null}
            </div>
          ))}
          <h4 style={{ marginTop: 16 }}>Out</h4>
          <div className="lu-out">{out.length ? out.map((i) => `${i.player} (${i.status})`).join(', ') : '—'}</div>
        </div>
      </div>
    </section>
  )
}

interface Props {
  board: Board
  gameId: string | null
  onPick: (id: string) => void
}

export function Lineups({ board, gameId, onPick }: Props) {
  const games = board.games
  const game: Game | undefined = games.find((g) => g.id === gameId) ?? games[0]
  const [tab, setTab] = useState<'lines' | 'changes' | 'analysis' | 'notes'>('lines')
  if (!game) return <div className="state-box">No games on this board.</div>
  const { away, home, markets, lineup } = game
  return (
    <>
      <div className="lu-topline">
        <div className="lu-matchup">
          <img src={LOGO(away.abbr)} alt="" />
          <div>
            <b>
              {away.city}
              <br />
              {away.name}
            </b>
            <small>({away.record})</small>
          </div>
          <span className="at">AT</span>
          <img src={LOGO(home.abbr)} alt="" />
          <div>
            <b>
              {home.city}
              <br />
              {home.name}
            </b>
            <small>({home.record})</small>
          </div>
        </div>
        <div className="lu-market">
          <div className="pill sel">
            {home.abbr} {markets.moneyline.home ?? '—'}
          </div>
          <div className="pill">
            {away.abbr} {markets.moneyline.away ?? '—'}
          </div>
        </div>
        <div className="lu-market">
          <div className="pill tall">
            <small>O/U</small>
            <b>{markets.total.line ?? '—'}</b>
          </div>
        </div>
        <div className="lu-when">
          <small>Puck Drop</small>
          <b>{etTime(game.start_utc)} ET</b>
          <small>{game.venue}</small>
        </div>
        <select className="lu-pick" aria-label="Choose game" value={game.id} onChange={(e) => onPick(e.target.value)}>
          {games.map((g) => (
            <option key={g.id} value={g.id}>
              {etTime(g.start_utc)} · {g.away.abbr} @ {g.home.abbr}
            </option>
          ))}
        </select>
      </div>

      <div className="lu-tabs" role="tablist">
        {(
          [
            ['lines', 'Lines & Lineups'],
            ['changes', '⇅ Line Changes'],
            ['analysis', 'Betting Analysis'],
            ['notes', 'Matchup Notes'],
          ] as const
        ).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'sel' : ''} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'lines' ? (
        <div className="lu-grid">
          <div className="lu-center">Projected Lineups</div>
          <TeamPanel lu={lineup?.away ?? null} team={away} side="AWAY" goalieStatus={away.goalie_status} />
          <TeamPanel lu={lineup?.home ?? null} team={home} side="HOME" goalieStatus={home.goalie_status} />
        </div>
      ) : (
        <div className="state-box" style={{ marginTop: 18 }}>
          Design pending for this tab.
        </div>
      )}
    </>
  )
}
