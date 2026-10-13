import { useState } from 'react'
import { api } from '../api'
import { Empty, ErrorRetry, Meter, PageHead, fmtDate, isoDay, useAction } from '../ui'

const TYPES = [['all', 'All'], ['interview', 'Mock interviews'], ['coach', 'Coach calls'], ['import', 'Imports']]
const TYPE_LABEL = { interview: 'Mock interview', coach: 'Coach call', import: 'Import' }
const TRANSCRIPT_LINK = { interview: 'View what you said in this interview', coach: 'View what you told the coach', import: 'View the text we read' }
const SCORE_LABELS = { structure: 'Structure', clarity: 'Clarity', evidence: 'Evidence', uk_tone: 'UK tone' }

// What was said in that session, fetched only when the user asks for it
function Transcript({ entry }) {
  const load = useAction(() => api(`/api/journal/${entry.id}/transcript`))
  if (load.result) return <pre className="draft small" style={{ marginTop: 8, fontFamily: 'inherit' }}>{load.result.transcript}</pre>
  return (
    <>
      <button className="linkish small" style={{ marginTop: 8 }} disabled={load.loading} onClick={() => load.run()}>
        {load.loading ? 'Loading' : TRANSCRIPT_LINK[entry.type]}
      </button>
      <ErrorRetry error={load.error} onRetry={load.retry} />
    </>
  )
}

export default function Journal({ s, go }) {
  const [type, setType] = useState('all')
  const entries = s.journal.filter((e) => type === 'all' || e.type === type)

  return (
    <>
      <PageHead title="Journal" lede="A log of every coach call, mock interview and import, with notes written for you after each one." />
      {s.journal.length === 0 ? (
        <Empty title="No sessions yet." body="Coach calls, mock interviews and imports are saved here automatically." action="Practise an interview" onAction={() => go('interview')} />
      ) : (
        <>
          <div className="filters">
            {TYPES.map(([k, l]) => (
              <button key={k} className={`filter ${type === k ? 'active' : ''}`} onClick={() => setType(k)}>
                {l} ({k === 'all' ? s.journal.length : s.journal.filter((e) => e.type === k).length})
              </button>
            ))}
          </div>
          <div className="card">
            {entries.length === 0 && <p className="muted">Nothing of this kind yet.</p>}
            <div className="list">
              {entries.map((e) => (
                <article key={e.id} className="journal-entry">
                  <div className="when">{fmtDate(isoDay(new Date(e.created_at)), { day: 'numeric', month: 'short', year: 'numeric' })}</div>
                  <div>
                    <div className="row" style={{ gap: 8 }}>
                      <span className="chip good">{TYPE_LABEL[e.type]}</span>
                      {e.with_whom && <span className="small muted">with {e.with_whom}</span>}
                    </div>
                    <h3 style={{ marginTop: 6, fontSize: 15.5 }}>{e.title}</h3>
                    <p className="small" style={{ marginTop: 2 }}>{e.summary}</p>
                    {(e.points.length > 0 || e.actions.length > 0 || e.scores) && (
                      <details>
                        <summary>Session notes</summary>
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
