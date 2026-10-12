import { useState } from 'react'
import { ClipboardList, Mic } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry, VISA_LABEL, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'

const MIN_CHARS = 20

/*
  How a user tells us their background: a voice call with the coach, or pasted text.
  Either way the text goes to the AI, which returns achievements. The text is kept
  in state, so a failed AI call can be retried without repeating the call or the paste.
*/
export default function BackgroundInput({ s, userId, onBuilt }) {
  const [mode, setMode] = useState('voice')
  const [text, setText] = useState('')
  const p = s.profile
  const build = useAction(async (transcript, source) => {
    const r = await post('/api/ai/achievements', { transcript, source })
    await onBuilt(r)
    return r
  })

  return (
    <div className="stack">
      <div className="grid cols-2">
        <button className={`card choice ${mode === 'voice' ? 'selected' : ''}`} onClick={() => setMode('voice')}>
          <span className="icon-box"><Mic size={19} /></span>
          <span><h3>Talk to our careers coach</h3><p>A 2 to 3 minute voice conversation. The coach asks the questions.</p></span>
        </button>
        <button className={`card choice ${mode === 'paste' ? 'selected' : ''}`} onClick={() => setMode('paste')}>
          <span className="icon-box"><ClipboardList size={19} /></span>
          <span><h3>Paste your CV or notes</h3><p>An old CV, your LinkedIn About section or rough notes all work.</p></span>
        </button>
      </div>

      {mode === 'voice' ? (
        <VoiceAgent
          agent="onboarding"
          agentLabel="Coach"
          intro="Start when you are ready"
          userId={userId}
          dynamicVariables={{ candidate_name: p.first_name || 'there', course: p.course || 'your course', university: p.university || 'your university', visa_type: VISA_LABEL[p.visa_type] || 'Student' }}
          onDone={(t) => build.run(t, 'voice')}
        />
      ) : (
        <div className="card">
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="I worked for two years at..." aria-label="Your CV or notes" />
          <div className="row" style={{ marginTop: 10 }}>
            <span className="small muted">{text.trim().length < MIN_CHARS ? 'Paste at least a few sentences.' : ''}</span>
            <span className="spacer" />
            <button className="btn" disabled={build.loading || text.trim().length < MIN_CHARS} onClick={() => build.run(text, 'paste')}>
              {build.loading ? 'Building your profile' : 'Build my profile'}
            </button>
          </div>
        </div>
      )}

      {build.loading && mode === 'voice' && <p className="muted" style={{ textAlign: 'center' }}>Building your profile</p>}
      <ErrorRetry error={build.error} onRetry={build.retry} />
    </div>
  )
}
