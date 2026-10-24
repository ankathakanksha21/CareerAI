import { useId, useState } from 'react'
import { ClipboardList, FileUp, FolderGit2, Mic } from 'lucide-react'
import { post, upload } from '../api'
import { ErrorRetry, VISA_LABEL, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'
import GitHubImport from './GitHubImport'

const MIN_CHARS = 20
const MAX_FILE_BYTES = 4 * 1024 * 1024 // the server's limit; checked here first so a large file is refused at once
const TOO_BIG = 'That file is over 4 MB. Upload a smaller one, or paste the text instead.'
const TILES = [
  { key: 'voice', icon: Mic, title: 'Talk to the coach', text: '2 to 3 minutes. The coach asks the questions.' },
  { key: 'upload', icon: FileUp, title: 'Upload your CV', text: 'PDF or Word (.docx), up to 4 MB' },
  { key: 'paste', icon: ClipboardList, title: 'Paste text', text: 'Old CV, LinkedIn About or rough notes' },
  { key: 'github', icon: FolderGit2, title: 'Add GitHub projects', text: 'Up to 5 of your own public repositories' },
]

/*
  How a user tells us their background: a voice call with the coach, a CV file, pasted text,
  or GitHub projects. Any of them, and more than one. Each ends in onBuilt(result), where
  result has the achievements saved, any CV facts found for the user to confirm, and a notice.
  What was said, pasted or picked stays in state, so a failed AI call can be retried.
*/
export default function BackgroundInput({ s, userId, onBuilt }) {
  const [mode, setMode] = useState('voice')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const p = s.profile
  const build = useAction(async (source, given) => {
    const r = source === 'cv'
      ? await upload('/api/ai/achievements/upload', given)
      : await post('/api/ai/achievements', { transcript: given, source })
    await onBuilt({ ...r, source })
    return r
  })
  const tooBig = file && file.size > MAX_FILE_BYTES
  const typed = text.trim().length
  const detailId = useId()
  const detail = TILES.find((t) => t.key === mode).text

  return (
    <div className="stack">
      <div className="background-tabs" role="group" aria-label="Ways to add your background">
        {TILES.map(({ key, icon: Icon, title }) => (
          <button key={key} className={`background-tab ${mode === key ? 'selected' : ''}`} onClick={() => setMode(key)} aria-pressed={mode === key}
            aria-describedby={mode === key ? detailId : undefined}>
            <Icon size={18} aria-hidden="true" />{title}
          </button>
        ))}
      </div>
      <p className="small muted background-detail" id={detailId}>{detail}</p>

      {mode === 'voice' && (
        <VoiceAgent
          agent="onboarding"
          agentLabel="Coach"
          intro="Coach call"
          userId={userId}
          dynamicVariables={{ candidate_name: p.first_name || 'there', course: p.course || 'your course', university: p.university || 'your university', visa_type: VISA_LABEL[p.visa_type] || 'Student' }}
          onDone={(t) => build.run('voice', t)}
        />
      )}

      {mode === 'upload' && (
        <div className="card stack">
          <label className="field">Your CV
            <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              disabled={build.loading} onChange={(e) => setFile(e.target.files[0] || null)} />
          </label>
          {tooBig && <p className="error" role="alert">{TOO_BIG}</p>}
          <div className="row">
            <span className="small muted">{build.loading ? 'Takes about half a minute.' : 'Read once and discarded. Only the text is kept.'}</span>
            <span className="spacer" />
            <button className="btn" disabled={build.loading || !file || tooBig} onClick={() => build.run('cv', file)}>
              {build.loading ? 'Reading your CV' : 'Build my profile'}
            </button>
          </div>
        </div>
      )}

      {mode === 'paste' && (
        <div className="card">
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder="I worked for two years at..." aria-label="Your CV or notes" />
          <div className="row" style={{ marginTop: 10 }}>
            <span className="small muted">{typed > 0 && typed < MIN_CHARS ? 'Paste at least a few sentences.' : ''}</span>
            <span className="spacer" />
            <button className="btn" disabled={build.loading || typed < MIN_CHARS} onClick={() => build.run('paste', text)}>
              {build.loading ? 'Building your profile' : 'Build my profile'}
            </button>
          </div>
        </div>
      )}

      {mode === 'github' && <GitHubImport s={s} onImported={(r) => onBuilt({ ...r, facts: null, source: 'github' })} />}

      {build.loading && mode === 'voice' && <p className="muted" style={{ textAlign: 'center' }}>Building your profile</p>}
      {/* a file that cannot be read will not read on a second try: no Retry for those */}
      {mode !== 'github' && <ErrorRetry error={build.error} onRetry={[413, 422].includes(build.error?.status) ? null : build.retry} />}
    </div>
  )
}
