import clsx from 'clsx'

export function Controls({ isCapturing, onStart, onStop, sessionId }) {
  return (
    <div className="flex items-center justify-between">
      <button
        onClick={isCapturing ? onStop : onStart}
        className={clsx(
          'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all active:scale-95',
          isCapturing
            ? 'bg-red-500/20 text-red-300 border border-red-500/40 hover:bg-red-500/30'
            : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30'
        )}
      >
        <span
          className={clsx(
            'w-2 h-2 rounded-full',
            isCapturing ? 'bg-red-400 animate-pulse' : 'bg-emerald-400'
          )}
        />
        {isCapturing ? 'Stop listening' : 'Start listening'}
      </button>

      {sessionId && (
        <span className="text-[10px] text-white/20 font-mono">
          {sessionId.slice(0, 8)}
        </span>
      )}
    </div>
  )
}
