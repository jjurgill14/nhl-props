// All puck-drop display and filtering is in America/New_York, DST-correct via Intl.
const ET = 'America/New_York'

const fmtTime = new Intl.DateTimeFormat('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit', hour12: true })
const fmtParts = new Intl.DateTimeFormat('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit', hour12: false })
const fmtDate = new Intl.DateTimeFormat('en-US', { timeZone: ET, weekday: 'short', month: 'short', day: 'numeric' })
const fmtStamp = new Intl.DateTimeFormat('en-US', { timeZone: ET, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

/** "7:30 PM" */
export function etTime(iso: string): string {
  return fmtTime.format(new Date(iso))
}

/** "Sat, Nov 7" */
export function etDate(iso: string): string {
  return fmtDate.format(new Date(iso))
}

/** "Nov 6, 7:59 PM" */
export function etStamp(iso: string | null): string {
  return iso ? fmtStamp.format(new Date(iso)) : '—'
}

/** Puck-drop bucket key used by the time chips, e.g. "7", "7:30", "12:30". */
export function etBucket(iso: string): string {
  const parts = fmtParts.formatToParts(new Date(iso))
  let h = Number(parts.find((p) => p.type === 'hour')?.value ?? 0)
  const m = parts.find((p) => p.type === 'minute')?.value ?? '00'
  if (h === 24) h = 0
  const h12 = h % 12 === 0 ? 12 : h % 12
  return m === '00' ? String(h12) : `${h12}:${m}`
}

/** Sort key for buckets in puck-drop order within a slate (afternoon before evening). */
export function bucketOrder(iso: string): number {
  const parts = fmtParts.formatToParts(new Date(iso))
  let h = Number(parts.find((p) => p.type === 'hour')?.value ?? 0)
  const m = Number(parts.find((p) => p.type === 'minute')?.value ?? 0)
  if (h === 24) h = 0
  return h * 60 + m
}

/** "Saturday, November 7" from a YYYY-MM-DD slate date (no TZ shift). */
export function longDate(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number)
  return new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(y, m - 1, d)),
  )
}
