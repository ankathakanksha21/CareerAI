import { post } from '../api'
import { ErrorRetry, useAction } from '../ui'

// The common UK competencies against the user's stories, with the gaps named
export default function StoryCoverage({ s, refresh, notify }) {
  const tag = useAction(async () => { await post('/api/ai/stories/tag'); await refresh(); notify('Stories tagged') })
  const untagged = s.stories.filter((st) => !st.competencies.length).length
  if (!s.stories.length) return null
  return (
    <section className="card" style={{ marginBottom: 16 }}>
      <h2>Story coverage</h2>
      <p className="sub">UK competency interviews come back to these eight. Aim for at least one story for each.</p>
      <div className="coverage">
        {s.options.competencies.map(([key, label]) => {
          const told = s.stories.filter((st) => st.competencies.includes(key))
          return (
            <div key={key} className={`coverage-row ${told.length ? '' : 'gap'}`}>
              <span className="strong">{label}</span>
              <span>{told.length ? told.map((st) => st.title).join(', ') : 'No story yet'}</span>
            </div>
          )
        })}
      </div>
      {untagged > 0 && (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn ghost small" disabled={tag.loading} onClick={() => tag.run()}>{tag.loading ? 'Tagging' : 'Tag my stories'}</button>
          <span className="small muted">{untagged === 1 ? '1 story has' : `${untagged} stories have`} no competencies yet. One AI action.</span>
        </div>
      )}
      <ErrorRetry error={tag.error} onRetry={tag.retry} />
    </section>
  )
}
