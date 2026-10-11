import { useEffect, useRef, useState } from 'react'
import { Conversation } from '@elevenlabs/client'
import { api } from './api'

/*
  One ElevenLabs agent call over WebRTC. The backend mints a short-lived
  conversation token, so the API key never reaches the browser. Transcript
  turns stream in through onMessage; when the call ends the full transcript
  is handed to onDone(text) for the AI to work on.
*/
export default function VoiceAgent({ agent, agentLabel, userId, dynamicVariables, color, onDone, intro, children }) {
  const [status, setStatus] = useState('idle') // idle | connecting | live | ended
  const [mode, setMode] = useState('listening')
  const [turns, setTurns] = useState([])
  const [error, setError] = useState(null)
  const conv = useRef(null)
  const turnsRef = useRef([])
  const doneRef = useRef(false)
  const convIdRef = useRef(null)
  const boxRef = useRef(null)

  useEffect(() => () => { conv.current?.endSession() }, [])
  useEffect(() => { boxRef.current?.scrollTo(0, boxRef.current.scrollHeight) }, [turns])

  const addTurn = ({ message, role, source, event_id }) => {
    const who = role || (source === 'ai' ? 'agent' : 'user')
    const next = [...turnsRef.current]
    const i = next.findIndex((t) => t.id === event_id && t.role === who)
    if (i >= 0) next[i] = { ...next[i], message }
    else next.push({ id: event_id, role: who, message })
    turnsRef.current = next
    setTurns(next)
  }

  const finish = async (id) => {
    if (doneRef.current) return
    doneRef.current = true
    setStatus('ended')
    let list = turnsRef.current
    if (!list.length && id) {
      // browser missed the turns: ask ElevenLabs for the stored transcript
      try {
        const r = await api(`/api/voice/transcript/${id}`)
        list = r.turns
        turnsRef.current = list
        setTurns(list)
      } catch { /* nothing to recover */ }
    }
    const text = list.map((t) => `${t.role === 'agent' ? agentLabel : 'Candidate'}: ${t.message}`).join('\n')
    if (text) onDone(text)
  }

  const start = async () => {
    setError(null)
    setTurns([])
    turnsRef.current = []
    doneRef.current = false
    convIdRef.current = null
    setStatus('connecting')
    const open = (auth) => Conversation.startSession({
      ...auth,
      userId, // tags the conversation with its owner, so only they can read its transcript
      dynamicVariables: { ...dynamicVariables, user_id: userId },
      onConnect: () => setStatus('live'),
      onMessage: addTurn,
      onModeChange: ({ mode }) => setMode(mode),
      onError: (msg) => setError(typeof msg === 'string' ? msg : 'Voice connection error'),
      onDisconnect: () => finish(convIdRef.current),
    })
    try {
      const { token } = await api(`/api/voice/token?agent=${agent}`) // fails fast if voice is not set up
      await navigator.mediaDevices.getUserMedia({ audio: true })
      try {
        conv.current = await open({ conversationToken: token, connectionType: 'webrtc' })
      } catch (rtcError) {
        // Some browsers, extensions or networks block the WebRTC host. Retry over a WebSocket via api.elevenlabs.io
        console.warn('WebRTC voice failed, retrying over WebSocket', rtcError)
        doneRef.current = false
        setError(null)
        setStatus('connecting')
        const { signed_url } = await api(`/api/voice/token?agent=${agent}&transport=websocket`)
        conv.current = await open({ signedUrl: signed_url, connectionType: 'websocket' })
      }
      convIdRef.current = conv.current.getId()
      setError(null)
      setStatus('live')
    } catch (e) {
      setStatus('idle')
      setError(e.name === 'NotAllowedError' ? 'Microphone access was blocked. Allow it in the browser and try again.' : e.message)
    }
  }

  const end = async () => {
    const c = conv.current
    conv.current = null
    await c?.endSession()
  }

  const speaking = status === 'live' && mode === 'speaking'
  return (
    <div className="voice" style={{ '--c': color }}>
      <div className="voice-head">
        <div className={`orb ${speaking ? 'speaking' : status === 'live' ? 'listening' : ''}`} aria-hidden>
          <span className="bars"><i /><i /><i /><i /></span>
        </div>
        <div style={{ flex: 1 }}>
          <div className="strong">
            {status === 'idle' && intro}
            {status === 'connecting' && 'Connecting'}
            {status === 'live' && (speaking ? `${agentLabel} is speaking` : 'Listening to you')}
            {status === 'ended' && 'Call ended'}
          </div>
          <div className="small muted">
            {status === 'live' ? 'Speak naturally. Press End when you are done.' : 'Uses your microphone. Your voice is processed by ElevenLabs to run and transcribe this call.'}
          </div>
        </div>
        {status === 'live' || status === 'connecting'
          ? <button className="btn danger" onClick={end}>End</button>
          : <button className="btn" onClick={start}>{status === 'ended' ? 'Start again' : 'Start talking'}</button>}
      </div>
      {error && <p className="error">{error}</p>}
      {/* Proof of what was heard: the user's words appear here as the call goes on, and stay after it ends */}
      {status !== 'idle' && (
        <div className="heard">
          <div className="heard-head">
            <span className="strong">{status === 'ended' ? 'Transcript of this call' : 'Live transcript'}</span>
            <span className="small muted">
              {status === 'ended' ? `Everything below is built from these words.` : `What the ${agentLabel.toLowerCase()} hears. Your words appear a moment after each sentence.`}
            </span>
          </div>
          <div className="transcript" ref={boxRef} aria-live="polite">
            {turns.length === 0 && <p className="small muted">{status === 'ended' ? 'Nothing was captured in this call.' : 'Nothing yet. Start speaking when you are ready.'}</p>}
            {turns.map((t, i) => (
              <div key={i} className={`turn ${t.role}`}>
                <span className="who">{t.role === 'agent' ? agentLabel : 'You said'}</span>
                {t.message}
              </div>
            ))}
          </div>
        </div>
      )}
      {children}
    </div>
  )
}
