import { ExternalLink, Search } from 'lucide-react'
import { ErrorRetry, InfoTip } from '../ui'

// LinkedIn searches for alumni of the user's university, at the companies they saved jobs from or in their target roles.
// The app fetches nothing: each link opens LinkedIn, with the search words shown in case it asks to sign in first
export default function FindPeople({ links, error, retry, go }) {
  const found = links && links.people.length > 0
  return (
    <section className="card">
      <div className="findpeople-head">
        <h2>Find people</h2>
        {found && (
          <InfoTip label="If the search does not open">
            Search lost after signing in to LinkedIn? Paste the words under the link into LinkedIn and choose People.
          </InfoTip>
        )}
      </div>
      <p className="sub">Alumni are your warmest first contacts.</p>
      <ErrorRetry error={error} onRetry={retry} />
      {links && links.people.length === 0 && (
        <p className="small" style={{ marginTop: 10 }}>Add your university to search its alumni. <button className="linkish small" onClick={() => go('profile')}>Open profile</button></p>
      )}
      {found && (
        <div className="list" style={{ marginTop: 10 }}>
          {links.people.map((l) => (
            <div key={l.url} className="link-row">
              <a href={l.url} target="_blank" rel="noopener noreferrer">{l.label} <ExternalLink size={13} /></a>
              <span className="small muted findpeople-terms">
                <Search size={12} role="img" aria-label="Search words"><title>Search words</title></Search>
                {l.terms}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
