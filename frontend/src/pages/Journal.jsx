import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { api } from '../api'
import { Empty, ErrorRetry, Meter, PageHead, Spinner, fmtDate, isoDay, useAction } from '../ui'

const TYPES = [['all', 'All'], ['interview', 'Mock interviews'], ['coach', 'Coach calls'], ['import', 'Imports']]
const TYPE_LABEL = { interview: 'Mock interview', coach: 'Coach call', import: 'Import' }
// A coach call is kept with both sides of it, and a pasted background is filed as a coach entry too,
// so the coach link is neutral and no link claims the words are only the user's
const TRANSCRIPT_LINK = { interview: 'Transcript', coach: 'Full text', import: 'Text we read' }
const SCORE_LABELS = { structure: 'Structure', clarity: 'Clarity', evidence: 'Evidence', uk_tone: 'UK tone' }

// "12 Oct" this year, "12 Oct 2025" before it
const when = (iso) => {
  const day = isoDay(new Date(iso))
  return day.slice(0, 4) === String(new Date().getFullYear()) ? fmtDate(day) : fmtDate(day, { day: 'numeric', month: 'short', year: 'numeric' })
}

// What was said in that session, fetched only when the user asks for it
function Transcript({ entry }) {
  const load = useAction(() => api(`/api/journal/${entry.id}/transcript`))
  if (load.result) return <pre className="draft small" style={{ marginTop: 8, fontFamily: 'inherit' }}>{load.result.transcript}</pre>
  return (
    <>
      <button className="linkish small journal-transcript" style={{ marginTop: 8 }} disabled={load.loading} onClick={() => load.run()}>
        {TRANSCRIPT_LINK[entry.type]}{load.loading ? <Spinner /> : <ChevronDown size={15} aria-hidden="true" />}
      </button>
      <ErrorRetry error={load.error} onRetry={load.retry} />
    </>
  )
}

export default function Journal({ s, go }) {
  const [type, setType] = useState('all')
  const entries = s.journal.filter((e) => type === 'all' || e.type === type)
  const count = (k) => (k === 'all' ? s.journal.length : s.journal.filter((e) => e.type === k).length)
  // Only kinds that have entries get a filter, and the row shows only when there is more than one kind
  const kinds = TYPES.filter(([k]) => k === 'all' || count(k) > 0)

  return (
    <>
      <PageHead title="Journal" />
      {s.journal.length === 0 ? (
        <Empty title="No sessions yet." body="Coach calls, mock interviews and imports appear here." action="Practise an interview" onAction={() => go('interview')} />
      ) : (
        <>
          {kinds.length > 2 && (
            <div className="filters">
              {kinds.map(([k, l]) => (
                <button key={k} className={`filter ${type === k ? 'active' : ''}`} onClick={() => setType(k)}>
                  {l} <span className="filter-count">{count(k)}</span>
                </button>
              ))}
            </div>
          )}
          <div className="card">
            {entries.length === 0 && <p className="muted">None yet.</p>}
            <div className="list">
              {entries.map((e) => (
                <article key={e.id} className="journal-entry">
                  <div className="when">{when(e.created_at)}</div>
                  <div>
                    <div className="row" style={{ gap: 8 }}>
                      <span className="chip good">{TYPE_LABEL[e.type]}</span>
                    </div>
                    <h3 style={{ marginTop: 6, fontSize: 15.5 }}>{e.title}</h3>
                    <p className="small" style={{ marginTop: 2 }}>{e.summary}</p>
                    {(e.points.length > 0 || e.actions.length > 0 || e.scores) && (
                      <details>
                        <summary>Notes</summary>
                        <div className="grid cols-2" style={{ marginTop: 10 }}>
                          {e.points.length > 0 && <div><h3>{e.type === 'interview' ? 'What worked' : e.type === 'import' ? 'Added' : 'Key points'}</h3><ul className="dots small">{e.points.map((x) => <li key={x}>{x}</li>)}</ul></div>}
                          {e.actions.length > 0 && <div><h3>{e.type === 'interview' ? 'Change next time' : 'Actions'}</h3><ul className="dots small">{e.actions.map((x) => <li key={x}>{x}</li>)}</ul></div>}
                          {e.scores && (
                            <div className="stack" style={{ gap: 6 }}>
                              {Object.entries(e.scores).map(([k, v]) => <div key={k} className="score small"><span>{SCORE_LABELS[k] || k}</span><Meter value={v * 20} /><b>{v}/5</b></div>)}
                            </div>
                          )}
                        </div>
                      </details>
                    )}
                    {e.has_transcript && <div><Transcript entry={e} /></div>}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
