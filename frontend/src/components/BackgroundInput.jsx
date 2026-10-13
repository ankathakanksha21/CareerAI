import { useState } from 'react'
import { ClipboardList, FileUp, FolderGit2, Mic } from 'lucide-react'
import { post, upload } from '../api'
import { ErrorRetry, VISA_LABEL, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'
import GitHubImport from './GitHubImport'

const MIN_CHARS = 20
const MAX_FILE_BYTES = 4 * 1024 * 1024 // the server's limit; checked here first so a large file is refused at once
const TOO_BIG = 'That file is over 4 MB. Upload a smaller one, or paste the text instead.'
const TILES = [
  { key: 'voice', icon: Mic, title: 'Talk to the coach', text: 'A 2 to 3 minute voice conversation. The coach asks the questions.' },
  { key: 'upload', icon: FileUp, title: 'Upload your CV', text: 'A PDF or Word file. We read it and do not keep the file.' },
  { key: 'paste', icon: ClipboardList, title: 'Paste text', text: 'An old CV, your LinkedIn About section or rough notes all work.' },
  { key: 'github', icon: FolderGit2, title: 'Add GitHub projects', text: 'Pick up to 5 of your own public repositories.' },
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

  return (
    <div className="stack">
      <div className="grid cols-2">
        {TILES.map(({ key, icon: Icon, title, text: blurb }) => (
          <button key={key} className={`card choice ${mode === key ? 'selected' : ''}`} onClick={() => setMode(key)} aria-pressed={mode === key}>
            <span className="icon-box"><Icon size={19} /></span>
            <span><h3>{title}</h3><p>{blurb}</p></span>
          </button>
        ))}
      </div>

      {mode === 'voice' && (
        <VoiceAgent
          agent="onboarding"
          agentLabel="Coach"
          intro="Start when you are ready"
          userId={userId}
          dynamicVariables={{ candidate_name: p.first_name || 'there', course: p.course || 'your course', university: p.university || 'your university', visa_type: VISA_LABEL[p.visa_type] || 'Student' }}
          onDone={(t) => build.run('voice', t)}
        />
      )}

      {mode === 'upload' && (
        <div className="card stack">
          <label className="field">Your CV, as a PDF or Word (.docx) file up to 4 MB
            <input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              disabled={build.loading} onChange={(e) => setFile(e.target.files[0] || null)} />
          </label>
          {tooBig && <p className="error" role="alert">{TOO_BIG}</p>}
          <div className="row">
            <span className="small muted">{build.loading ? 'Reading your CV. This takes about half a minute.' : 'The file is read once and discarded. Only its text is kept.'}</span>
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
            <span className="small muted">{text.trim().length < MIN_CHARS ? 'Paste at least a few sentences.' : ''}</span>
            <span className="spacer" />
            <button className="btn" disabled={build.loading || text.trim().length < MIN_CHARS} onClick={() => build.run('paste', text)}>
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
