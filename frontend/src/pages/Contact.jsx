import { ExternalLink, Mail } from 'lucide-react'
import { Avatar, Brand } from '../ui'

// The two people who build UK Career Navigator, as they gave their details (25 Oct 2026). Email and LinkedIn
// only: their phone numbers are kept off this public page on purpose
const OWNERS = [
  { name: 'Akanksha Ankath', email: 'akankshaankath@gmail.com', linkedin: 'https://www.linkedin.com/in/akanksha-ankath/' },
  { name: 'Dharan Teja Vipparla', email: 'dharantejavipparla@gmail.com', linkedin: 'https://www.linkedin.com/in/dharan-teja-vipparla-0a1104171/' },
]

// Contact us: open to anyone, signed in or not, like the privacy notice
export default function Contact({ go, signedIn }) {
  const back = () => go(signedIn ? 'home' : 'landing')
  return (
    <div>
      <header className="ob-top">
        <Brand onClick={back} />
        <span className="spacer" />
        <button className="linkish small" onClick={back}>Back</button>
      </header>
      <main className="ob-body">
        <div className="ob-title">
          <h1>Contact us</h1>
          <p>Questions, feedback or ideas? Write to either of us.</p>
        </div>
        <div className="grid cols-2 contact-cards">
          {OWNERS.map((o) => (
            <section key={o.email} className="card contact-card">
              <Avatar name={o.name} size="lg" />
              <h2>{o.name}</h2>
              <a className="contact-email" href={`mailto:${o.email}`}><Mail size={15} aria-hidden="true" />{o.email}</a>
              <a className="btn ghost small" href={o.linkedin} target="_blank" rel="noopener noreferrer">
                LinkedIn<ExternalLink size={14} aria-hidden="true" />
              </a>
            </section>
          ))}
        </div>
      </main>
    </div>
  )
}
