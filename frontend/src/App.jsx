import { useState, useCallback, useEffect, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useAudioCapture } from './hooks/useAudioCapture'
import { AnswerPanel } from './components/AnswerPanel'
import { TranscriptFeed } from './components/TranscriptFeed'
import { Controls } from './components/Controls'
import { StatusBadge } from './components/StatusBadge'
import './index.css'

const BACKEND_HTTP = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const MAX_TRANSCRIPT_LINES = 100

function App() {
  const [sessionId, setSessionId] = useState(null)
  const [transcript, setTranscript] = useState([])
  const [currentQuestion, setCurrentQuestion] = useState('')
  const [currentAnswer, setCurrentAnswer] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [isCapturing, setIsCapturing] = useState(false)
  const answerBufRef = useRef('')

  // ── fetch a new session from backend ────────────────────────────────────────
  useEffect(() => {
    fetch(`${BACKEND_HTTP}/new-session`)
      .then((r) => r.json())
      .then(({ session_id }) => setSessionId(session_id))
      .catch(() => {
        // Fallback: generate client-side UUID
        setSessionId(crypto.randomUUID())
      })
  }, [])

  // ── handle clear answer shortcut ───────────────────────────────────────────
  useEffect(() => {
    if (window.electronAPI?.onClearAnswer) {
      window.electronAPI.onClearAnswer(() => {
        setCurrentQuestion('')
        setCurrentAnswer('')
        answerBufRef.current = ''
        setIsStreaming(false)
      })

      return () => {
        window.electronAPI.removeAllListeners('clear-answer')
      }
    }
  }, [])

  // ── WebSocket message dispatcher ─────────────────────────────────────────────
  const handleMessage = useCallback((frame) => {
    switch (frame.type) {
      case 'transcript_ack':
        setTranscript((prev) => {
          const next = [...prev, { text: frame.text, speaker: 'them', ts: Date.now() }]
          return next.slice(-MAX_TRANSCRIPT_LINES)
        })
        break

      case 'question_detected':
        setCurrentQuestion(frame.text)
        setCurrentAnswer('')
        answerBufRef.current = ''
        setIsStreaming(true)
        break

      case 'answer_token':
        answerBufRef.current += frame.token
        setCurrentAnswer(answerBufRef.current)
        break

      case 'answer_done':
        setIsStreaming(false)
        break

      case 'error':
        console.error('[Server error]', frame.message)
        setIsStreaming(false)
        break

      case 'pong':
        break

      default:
        break
    }
  }, [])

  const { status, sendTranscript, disconnect, sendFrame } = useWebSocket({
    sessionId,
    onMessage: handleMessage,
  })

  // ── audio capture (browser fallback) ────────────────────────────────────────
  // In Electron, the backend captures audio via sounddevice.
  // In browser/dev mode, we use the browser mic and send chunks.
  const { start: startAudio, stop: stopAudio } = useAudioCapture({
    onTranscript: (frame) => {
      sendFrame(frame)
    },
    enabled: isCapturing,
  })

  const handleStart = () => {
    setIsCapturing(true)
    // Notify backend to start its own audio capture (via REST)
    fetch(`${BACKEND_HTTP}/capture/start`, { method: 'POST' }).catch(() => {})
    startAudio()
  }

  const handleStop = () => {
    setIsCapturing(false)
    fetch(`${BACKEND_HTTP}/capture/stop`, { method: 'POST' }).catch(() => {})
    stopAudio()
  }

  // ── dev shortcut: manually inject a test question ────────────────────────────
  const injectTest = () => {
    const testQuestion = 'Can you walk us through your approach to this project?'
    sendTranscript(testQuestion, 'interviewer')
  }

  return (
    <div
      className="min-h-screen flex items-start justify-start p-3"
      style={{ background: 'transparent' }}
    >
      {/* Overlay card */}
      <div className="w-[420px] rounded-2xl border border-white/10 bg-surface shadow-2xl overflow-hidden">
        {/* Header */}
        <div 
          className="flex items-center justify-between px-4 py-3 border-b border-white/5 select-none"
          style={{ WebkitAppRegion: 'drag', cursor: 'grab' }}
        >
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
            <span className="text-sm font-semibold text-white/80 tracking-tight">
              Meeting AI
            </span>
          </div>
          <StatusBadge status={status} />
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {/* Controls */}
          <Controls
            isCapturing={isCapturing}
            onStart={handleStart}
            onStop={handleStop}
            sessionId={sessionId}
          />

          {/* Answer panel */}
          <AnswerPanel
            question={currentQuestion}
            answer={currentAnswer}
            streaming={isStreaming}
          />

          {/* Transcript */}
          {transcript.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-white/30">
                Transcript
              </p>
              <TranscriptFeed lines={transcript} />
            </div>
          )}

          {/* Dev helper (remove in prod) */}
          {import.meta.env.DEV && (
            <button
              onClick={injectTest}
              className="w-full text-xs text-white/20 hover:text-white/40 py-1 transition-colors"
            >
              inject test question
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
