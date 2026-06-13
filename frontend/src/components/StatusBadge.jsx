import clsx from 'clsx'

const LABELS = {
  connected: 'Live',
  connecting: 'Connecting…',
  disconnected: 'Offline',
  error: 'Error',
}

const COLORS = {
  connected: 'bg-emerald-400',
  connecting: 'bg-amber-400 animate-pulse',
  disconnected: 'bg-zinc-500',
  error: 'bg-red-500',
}

export function StatusBadge({ status }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={clsx('w-2 h-2 rounded-full', COLORS[status])} />
      <span className="text-xs text-white/60 tabular-nums">{LABELS[status]}</span>
    </div>
  )
}
