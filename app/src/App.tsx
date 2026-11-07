import { useCallback, useEffect, useState } from 'react'
import './board.css'
import { Shell, type Route } from './components/Shell'
import { Board } from './pages/Board'
import { Placeholder } from './pages/Placeholder'
import { Lineups } from './pages/Lineups'
import { PropsPage, type PropsTarget } from './pages/Props'
import { loadBoard } from './data/load'
import type { LoadState } from './data/types'

const DEMO_SNAPSHOT = '2026-11-06' // a real, graded past slate; labeled as such wherever it shows

export default function App() {
  const [route, setRoute] = useState<Route>('slate')
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [gameId, setGameId] = useState<string | null>(null)
  const [propsTarget, setPropsTarget] = useState<PropsTarget>({ players: [] })
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
      {route !== 'slate' && route !== 'lineups' && route !== 'props' ? (
        <Placeholder route={route} />
      ) : state.kind === 'loading' ? (
        <div className="state-box" style={{ marginTop: 40 }}>
          Loading the board…
        </div>
      ) : state.kind === 'error' ? (
        <div className="state-box err" style={{ marginTop: 40 }}>
          Couldn't load the board ({state.message}). The pipeline writes it each morning; if it's early, check back after 6 AM ET.
        </div>
      ) : route === 'props' ? (
        <PropsPage board={state.board} target={propsTarget} onChange={setPropsTarget} />
      ) : route === 'lineups' ? (
        <Lineups board={state.board} gameId={gameId} onPick={setGameId} onPlayer={(id) => openProps({ players: [id] })} />
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
        />
      )}
    </Shell>
  )
}
