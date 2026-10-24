import { Fragment, useState } from 'react'
import { Check, Star } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry, fmtMonth, useAction } from '../ui'

const MAX_REPOS = 5
const USERNAME = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/ // GitHub's own rule
// People paste "@name" or their profile address as often as the bare name
const cleanName = (typed) => typed.trim().replace(/^@/, '').replace(/^https?:\/\/(www\.)?github\.com\//i, '').replace(/\/.*$/, '')

// A repository's language, stars and last update, separated by dots. The star count is read out in words
function RepoMeta({ r }) {
  const stars = `${r.stars} ${r.stars === 1 ? 'star' : 'stars'}`
  const parts = [
    r.language,
    r.stars ? <span key="stars" className="github-stars"><span role="img" aria-label={stars} title={stars}><Star size={12} aria-hidden="true" /></span><span aria-hidden="true">{r.stars}</span></span> : null,
    r.pushed_on ? `updated ${fmtMonth(r.pushed_on)}` : null,
  ].filter(Boolean)
  return parts.map((x, i) => <Fragment key={i}>{i > 0 && ' · '}{x}</Fragment>)
}

// Pick up to five of a GitHub user's own public repositories; each becomes a project achievement
export default function GitHubImport({ s, onImported }) {
  const [typed, setTyped] = useState(s.profile.github_username || '')
  const [picked, setPicked] = useState([])
  const [invalid, setInvalid] = useState(false)
  const list = useAction((name) => post('/api/github/repos', { username: name }))
  const run = useAction(async (username, repos) => {
    const r = await post('/api/ai/achievements/github', { username, repos })
    setPicked([])
    await onImported(r)
    list.run(username) // the list now shows which ones are imported
    return r
  })

  const find = (e) => {
    e.preventDefault()
    const name = cleanName(typed)
    setInvalid(!USERNAME.test(name))
    setPicked([])
    if (USERNAME.test(name)) list.run(name)
  }
  const toggle = (name) => setPicked(picked.includes(name) ? picked.filter((x) => x !== name) : [...picked, name])
  const found = list.result
  const open = found ? found.repos.filter((r) => !r.imported) : []

  return (
    <div className="card stack">
      <form className="form-row" onSubmit={find}>
        <label className="field" style={{ flex: 1, minWidth: 220 }}>GitHub username
          <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="e.g. octocat" autoCapitalize="none" autoCorrect="off" spellCheck={false} />
        </label>
        <button className="btn" type="submit" disabled={list.loading || !typed.trim()}>{list.loading ? 'Looking' : 'Find repositories'}</button>
      </form>
      {invalid && <p className="error" role="alert">Enter a GitHub username, for example octocat.</p>}
      <ErrorRetry error={list.error} onRetry={list.retry} />

      {found && !list.loading && (
        found.repos.length === 0 ? (
          <p className="muted">{found.username} has no public repositories of their own. Forks are left out.</p>
        ) : (
          <>
            <p className="small muted">Forks are left out. We read each one's description and README.</p>
            <div className="list">
              {found.repos.map((r) => (
                <label key={r.name} className="repo">
                  <input type="checkbox" checked={picked.includes(r.name)} disabled={r.imported || run.loading || (picked.length >= MAX_REPOS && !picked.includes(r.name))} onChange={() => toggle(r.name)} />
                  <span>
                    <span className="strong">{r.name}</span>
                    {r.imported && <span className="chip good" style={{ marginLeft: 8 }}><Check size={12} strokeWidth={3} aria-hidden="true" />Added</span>}
                    {r.description && <span className="small" style={{ display: 'block' }}>{r.description}</span>}
                    <span className="small muted" style={{ display: 'block' }}>
                      <RepoMeta r={r} />
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <div className="row">
              <span className="small muted">
                {run.loading ? 'Takes about 15 seconds.' : open.length === 0 ? 'All of these are already added.' : `${picked.length}/${MAX_REPOS} chosen`}
              </span>
              <span className="spacer" />
              <button className="btn" disabled={run.loading || picked.length === 0} onClick={() => run.run(found.username, picked)}>
                {run.loading ? 'Importing' : picked.length > 1 ? `Import ${picked.length} projects` : 'Import project'}
              </button>
            </div>
          </>
        )
      )}
      {run.result?.notice && !run.loading && <p className="small muted" role="status">{run.result.notice}</p>}
      <ErrorRetry error={run.error} onRetry={run.retry} />
    </div>
  )
}
