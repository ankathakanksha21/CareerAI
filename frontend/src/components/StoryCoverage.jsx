import { useId, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry, InfoTip, useAction } from '../ui'

// The common UK competencies against the user's stories, with the gaps named.
// A covered row shows how many stories; its titles open on click
export default function StoryCoverage({ s, refresh, notify }) {
  const tag = useAction(async () => { await post('/api/ai/stories/tag'); await refresh(); notify('Stories tagged') })
  const [open, setOpen] = useState([]) // competencies whose story titles are showing
  const id = useId()
  const untagged = s.stories.filter((st) => !st.competencies.length).length
  if (!s.stories.length) return null
  const total = s.options.competencies.length
  const covered = s.options.competencies.filter(([key]) => s.stories.some((st) => st.competencies.includes(key))).length
  const toggle = (key) => setOpen(open.includes(key) ? open.filter((k) => k !== key) : [...open, key])
  return (
    <section className="card" style={{ marginBottom: 16 }}>
      <div className="row coverage-head">
        <h2>Story coverage</h2>
        <span className={`chip ${covered === total ? 'good' : 'muted'}`}>{covered} of {total} covered</span>
        <InfoTip label="Why these competencies">UK competency interviews come back to these. Aim for one story each.</InfoTip>
      </div>
      <div className="coverage">
        {s.options.competencies.map(([key, label]) => {
          const told = s.stories.filter((st) => st.competencies.includes(key))
          const shown = open.includes(key)
          return (
            <div key={key} className={`coverage-row ${told.length ? '' : 'gap'}`}>
              <span className="strong">{label}</span>
              {told.length ? (
                <div>
                  <button type="button" className="coverage-count" aria-expanded={shown} aria-controls={`${id}-${key}`} onClick={() => toggle(key)}>
                    <Check size={14} aria-hidden="true" />{told.length === 1 ? '1 story' : `${told.length} stories`}
                    <ChevronDown size={14} aria-hidden="true" className={shown ? 'flip' : ''} />
                  </button>
                  <ul id={`${id}-${key}`} className="plain small muted coverage-titles" hidden={!shown}>
                    {told.map((st) => <li key={st.id}>{st.title}</li>)}
                  </ul>
                </div>
              ) : <span>No story yet</span>}
            </div>
          )
        })}
      </div>
      {untagged > 0 && (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn ghost small" disabled={tag.loading} onClick={() => tag.run()}>{tag.loading ? 'Tagging' : 'Tag my stories'}</button>
          <span className="small muted">{untagged === 1 ? '1 story' : `${untagged} stories`} untagged. One AI action.</span>
        </div>
      )}
      <ErrorRetry error={tag.error} onRetry={tag.retry} />
    </section>
  )
}
