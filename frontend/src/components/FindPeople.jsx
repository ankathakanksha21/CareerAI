import { ExternalLink } from 'lucide-react'
import { ErrorRetry } from '../ui'

// LinkedIn searches for alumni of the user's university, at the companies they saved jobs from or in their target roles.
// The app fetches nothing: each link opens LinkedIn, with the search words shown in case it asks to sign in first
export default function FindPeople({ links, error, retry, go }) {
  return (
    <section className="card">
      <h2>Find people</h2>
      <p className="sub">Alumni of your university are the warmest first contacts: you already share something real.</p>
      <ErrorRetry error={error} onRetry={retry} />
      {links && links.people.length === 0 && (
        <p className="small" style={{ marginTop: 10 }}>Add your university in your profile to search for its alumni. <button className="linkish small" onClick={() => go('profile')}>Open profile</button></p>
      )}
      {links && links.people.length > 0 && (
        <>
          <div className="list" style={{ marginTop: 10 }}>
            {links.people.map((l) => (
              <div key={l.url} className="link-row">
                <a href={l.url} target="_blank" rel="noopener noreferrer">{l.label} <ExternalLink size={13} /></a>
                <span className="small muted">Search words: {l.terms}</span>
              </div>
            ))}
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>LinkedIn asks you to sign in first. If the search does not open, paste the search words into LinkedIn and choose People.</p>
        </>
      )}
    </section>
  )
}
