import { useEffect, useRef } from 'react'
import clsx from 'clsx'

/**
 * TranscriptFeed
 *
 * Props:
 *   lines  {Array<{text, speaker, ts}>}  — transcript lines
 */
export function TranscriptFeed({ lines }) {
  const bottomRef = useRef(null)

  // Auto-scroll to bottom on new lines
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines.length])

  if (!lines.length) {
    return (
      <p className="text-xs text-white/30 text-center py-4">
        Transcript will appear here…
      </p>
    )
  }

  return (
    <div className="space-y-1 overflow-y-auto max-h-40 scroll-thin pr-1">
      {lines.map((line, i) => (
        <div key={i} className="flex items-start gap-2 animate-fade-in">
          <span
            className={clsx(
              'shrink-0 mt-0.5 text-[10px] font-semibold uppercase tracking-wider',
              line.speaker === 'user' ? 'text-violet-400/70' : 'text-zinc-500'
            )}
          >
            {line.speaker?.slice(0, 3) ?? 'UNK'}
          </span>
          <p className="text-xs text-white/70 leading-snug">{line.text}</p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
