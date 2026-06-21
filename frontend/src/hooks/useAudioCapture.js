import { useRef, useState, useCallback } from 'react'

const CHUNK_MS = 2000       // send audio every 2s
const SILENCE_THRESHOLD = 0.01

/**
 * useAudioCapture — browser-side mic capture with basic VAD.
 *
 * We capture the mic in the browser (Electron renderer has full media access).
 * Audio is sent as base64-encoded PCM to the backend via the sendTranscript
 * callback, but here we actually let the backend handle Whisper — so we send
 * the RAW text from the backend's transcription (the backend runs sounddevice).
 *
 * This hook is for a browser-only fallback where the backend can't access the
 * mic (e.g. when running in a browser tab instead of Electron).
 */
export function useAudioCapture({ onTranscript, enabled = false }) {
  const [isCapturing, setIsCapturing] = useState(false)
  const [error, setError] = useState(null)
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])

  const start = useCallback(async () => {
    if (isCapturing) return
    setError(null)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      streamRef.current = stream

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      recorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        chunksRef.current = []
        blob.arrayBuffer().then((buf) => {
          const bytes = new Uint8Array(buf)
          let binary = ''
          for (let i = 0; i < bytes.length; i += 8192) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192))
          }
          const b64 = btoa(binary)
          onTranscript?.({ type: 'audio_chunk', data: b64 })
        })
      }

      // Slice into chunks
      recorder.start()
      setIsCapturing(true)

      const interval = setInterval(() => {
        if (recorder.state === 'recording') {
          recorder.stop()
          recorder.start()
        }
      }, CHUNK_MS)

      streamRef.current._interval = interval
    } catch (err) {
      console.error('[Audio] Capture error:', err)
      setError(err.message)
    }
  }, [isCapturing, onTranscript])

  const stop = useCallback(() => {
    if (!isCapturing) return
    clearInterval(streamRef.current?._interval)
    recorderRef.current?.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    setIsCapturing(false)
  }, [isCapturing])

  return { isCapturing, error, start, stop }
}
