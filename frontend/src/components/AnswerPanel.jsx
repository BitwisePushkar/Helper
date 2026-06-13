import clsx from 'clsx'

/**
 * AnswerPanel
 *
 * Props:
 *   question  {string}  — detected question text
 *   answer    {string}  — accumulated tokens so far
 *   streaming {boolean} — true while tokens are still arriving
 */
export function AnswerPanel({ question, answer, streaming }) {
  if (!question && !answer) return null

  return (
    <div className="animate-fade-in rounded-xl border border-blue-500/30 bg-blue-950/40 p-4 space-y-2">
      {/* Question */}
      {question && (
        <div className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0 text-[10px] font-semibold tracking-widest uppercase text-blue-400/70">
            Q
          </span>
          <p className="text-sm text-blue-200/80 leading-snug">{question}</p>
        </div>
      )}

      {/* Divider */}
      {question && answer && (
        <div className="border-t border-white/5" />
      )}

      {/* Answer */}
      {answer && (
        <div className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0 text-[10px] font-semibold tracking-widest uppercase text-emerald-400/70">
            A
          </span>
          <p
            className={clsx(
              'text-sm text-white/90 leading-relaxed',
              streaming && 'cursor-blink'
            )}
          >
            {answer}
          </p>
        </div>
      )}

      {/* Streaming dots while question detected but no tokens yet */}
      {streaming && !answer && (
        <div className="flex items-center gap-1 pl-6">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse-dot"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
