import { ExternalLink } from 'lucide-react'
import { Chips, ShowMore } from '../ui'

// How networking works in the UK: fixed, checked guidance with its sources. Nothing here comes from the AI.
// Each card shows its title and opening line, with the rest under Read more; its sources stay in view
export default function NetworkingGuide({ s }) {
  return (
    <div className="grid cols-2 guide">
      {s.content.networking_guide.map((section, i) => {
        // a card with no intro opens with its first point, so its key fact is never hidden
        const lead = section.intro || section.points?.[0]
        const points = (section.intro ? section.points : section.points?.slice(1)) || []
        const more = Boolean(section.steps?.length || points.length || section.note)
        return (
          <section key={section.id} className="card">
            <h2>{section.title}</h2>
            {lead && <p className="sub">{lead}</p>}
            {more && (
              <ShowMore label="Read more" openLabel="Read less" defaultOpen={i === 0} className="guide-more">
                {section.steps && <ol className="steps guide-steps">{section.steps.map((t) => <li key={t}>{t}</li>)}</ol>}
                {points.length > 0 && <ul className="guide-list">{points.map((t) => <li key={t}>{t}</li>)}</ul>}
                {section.note && <p className="small muted">{section.note}</p>}
              </ShowMore>
            )}
            {section.sources?.length > 0 && (
              <Chips className="guide-sources" tone="muted" items={section.sources.map((src) => (
                <a key={src.url} href={src.url} target="_blank" rel="noopener noreferrer">{src.label} <ExternalLink size={12} /></a>
              ))} />
            )}
          </section>
        )
      })}
    </div>
  )
}
