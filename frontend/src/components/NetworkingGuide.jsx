import { ExternalLink } from 'lucide-react'

// How networking works in the UK: fixed, checked guidance with its sources. Nothing here comes from the AI
export default function NetworkingGuide({ s }) {
  return (
    <div className="grid cols-2 guide">
      {s.content.networking_guide.map((section) => (
        <section key={section.id} className="card">
          <h2>{section.title}</h2>
          {section.intro && <p className="sub">{section.intro}</p>}
          {section.steps && <ol className="guide-list">{section.steps.map((t) => <li key={t}>{t}</li>)}</ol>}
          {section.points && <ul className="guide-list">{section.points.map((t) => <li key={t}>{t}</li>)}</ul>}
          {section.note && <p className="small muted">{section.note}</p>}
          {section.sources?.length > 0 && (
            <p className="small" style={{ marginTop: 10 }}>
              {section.sources.map((src, i) => (
                <span key={src.url}>{i > 0 && ' · '}<a href={src.url} target="_blank" rel="noopener noreferrer">{src.label} <ExternalLink size={12} /></a></span>
              ))}
            </p>
          )}
        </section>
      ))}
    </div>
  )
}
