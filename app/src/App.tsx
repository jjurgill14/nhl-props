import { useCallback, useEffect, useState } from 'react'
import './board.css'
import { Shell, type Route } from './components/Shell'
import { Board } from './pages/Board'
import { Placeholder } from './pages/Placeholder'
import { Lineups } from './pages/Lineups'
import { PropsPage, type PropsTarget } from './pages/Props'
import { TeamRatesPage } from './pages/TeamRates'
import { MatchupPage } from './pages/Matchup'
import { DEFAULT_SPLIT } from './data/splits'
import { loadBoard } from './data/load'
import type { LoadState, SplitSel } from './data/types'

const DEMO_SNAPSHOT = '2026-11-06' // a real, graded past slate; labeled as such wherever it shows

export default function App() {
  const [route, setRoute] = useState<Route>('slate')
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [gameId, setGameId] = useState<string | null>(null)
  const [propsTarget, setPropsTarget] = useState<PropsTarget>({ players: [] })
  const [sel, setSel] = useState<SplitSel>(DEFAULT_SPLIT) // window / venue / defense view, shared by the board and the matchup page
  const openProps = (t: PropsTarget) => {
    if (!t.players.length) return
    setPropsTarget(t)
    setRoute('props')
  }

  const load = useCallback((date: string | null) => {
    setState({ kind: 'loading' })
    loadBoard(date ?? undefined)
      .then((board) => setState({ kind: 'ready', board }))
      .catch((e: Error) => setState({ kind: 'error', message: e.message }))
  }, [])

  useEffect(() => load(snapshot), [snapshot, load])

  const mode = state.kind === 'ready' ? state.board.mode : 'live'
  const statusLabel = state.kind === 'ready' ? (state.board.mode === 'live' ? 'LIVE BOARD' : 'SNAPSHOT') : 'LOADING'

  const snapshotControls = (
    <button
      type="button"
      className={snapshot ? 'selected' : ''}
      aria-pressed={!!snapshot}
      title="Toggle between tonight's live board and a labeled past snapshot"
      onClick={() => setSnapshot(snapshot ? null : DEMO_SNAPSHOT)}
    >
      {snapshot ? `Snapshot ${snapshot}` : 'Tonight'}
    </button>
  )

  return (
    <Shell route={route} onRoute={setRoute} mode={mode} statusLabel={statusLabel}>
      {route !== 'slate' && route !== 'lineups' && route !== 'props' && route !== 'rates' && route !== 'search' && route !== 'matchup' ? (
        <Placeholder route={route} />
      ) : state.kind === 'loading' ? (
        <div className="state-box" style={{ marginTop: 40 }}>
          Loading the board…
        </div>
      ) : state.kind === 'error' ? (
        <div className="state-box err" style={{ marginTop: 40 }}>
          Couldn't load the board ({state.message}). The pipeline writes it each morning; if it's early, check back after 6 AM ET.
        </div>
      ) : route === 'rates' ? (
        <TeamRatesPage board={state.board} />
      ) : route === 'props' || route === 'search' ? (
        <PropsPage board={state.board} target={route === 'search' ? { players: [] } : propsTarget} onChange={(t) => { setPropsTarget(t); setRoute('props') }} searchFocus={route === 'search'} />
      ) : route === 'matchup' ? (
        <MatchupPage
          board={state.board}
          gameId={gameId}
          onPick={setGameId}
          sel={sel}
          onSel={setSel}
          onBack={() => setRoute('slate')}
          onLineups={(id) => {
            setGameId(id)
            setRoute('lineups')
          }}
          onProps={openProps}
        />
      ) : route === 'lineups' ? (
        <Lineups board={state.board} gameId={gameId} onPick={setGameId} onPlayer={(id) => openProps({ players: [id] })} onGroup={(ids) => openProps({ players: ids.slice(0, 3), sort: 'best' })} />
      ) : (
        <Board
          key={state.board.date + state.board.mode}
          board={state.board}
          snapshotControls={snapshotControls}
          onLineups={(id) => {
            setGameId(id)
            setRoute('lineups')
          }}
          onProps={openProps}
          onMatchup={(id) => {
            setGameId(id)
            setRoute('matchup')
            window.scrollTo(0, 0)
          }}
          sel={sel}
          onSel={setSel}
        />
      )}
    </Shell>
  )
}
