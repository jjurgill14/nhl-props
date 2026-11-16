// "DFO updated <when> · checked <when>": the first is Daily Faceoff's own timestamp (what you
// actually care about — did they post post-skate lines?), the second is when we last pulled.
// Amber when DFO's lines predate game day, red when we have no snapshot for today at all.
import { etStamp, etYmd } from '../data/time'

interface Props {
  asOf: string | null
  checked?: string | null
  stale: boolean
  gameDate: string
}

export function LineupStamp({ asOf, checked, stale, gameDate }: Props) {
  const old = !stale && asOf != null && etYmd(asOf) !== gameDate
  return (
    <span className={`lu-stamp${stale ? ' stale' : old ? ' old' : ''}`} title={checked ? `last checked ${etStamp(checked)} ET` : undefined}>
      {stale ? <b className="warn">last known lineup</b> : old ? <b className="warn-soft">DFO not updated today</b> : 'DFO updated'} {etStamp(asOf)} ET
      {checked && checked !== asOf ? <span className="lu-checked"> · checked {etStamp(checked)} ET</span> : null}
    </span>
  )
}
