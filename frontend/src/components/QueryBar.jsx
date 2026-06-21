import { useState } from 'react'

export function QueryBar({ onSubmit, disabled }) {
  const [text, setText] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setText('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a question..."
        disabled={disabled}
        className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 placeholder-white/30 outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/30 disabled:opacity-40"
      />
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="rounded-lg bg-blue-500/20 border border-blue-500/40 px-3 py-2 text-sm font-medium text-blue-300 hover:bg-blue-500/30 active:scale-95 transition-all disabled:opacity-40 disabled:pointer-events-none"
      >
        Ask
      </button>
    </form>
  )
}
