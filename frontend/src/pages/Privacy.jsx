import { useEffect, useState } from 'react'
import { getConfig } from '../supabase'
import { Brand } from '../ui'

// A plain statement of what the app stores and who processes it. Draft: review before a public launch.
export default function Privacy({ go, signedIn }) {
  const [contact, setContact] = useState('')
  useEffect(() => { getConfig().then((c) => setContact(c.contact_email || '')).catch(() => {}) }, [])

  return (
    <div>
      <header className="ob-top">
        <Brand onClick={() => go(signedIn ? 'home' : 'landing')} />
        <span className="spacer" />
        <button className="linkish small" onClick={() => go(signedIn ? 'home' : 'landing')}>{signedIn ? 'Back to the app' : 'Back'}</button>
      </header>
      <main className="ob-body prose">
        <h1>Privacy notice</h1>
        <p className="muted">How UK Career Navigator uses your information.</p>

        <h2>What we collect</h2>
        <ul className="dots">
          <li>Your email address and name.</li>
          <li>Your university, course, graduation date, visa type, visa end date and preferred locations.</li>
          <li>What you tell the careers coach in a voice call, or paste into the app, about your background.</li>
          <li>Job descriptions you add, which matched jobs you save or dismiss, and the applications you log.</li>
          <li>Content the AI writes for you: achievements, CVs, cover letters, interview stories and feedback.</li>
          <li>A count of how many AI actions and voice calls you use each day.</li>
        </ul>

        <h2>Why we use it</h2>
        <p>To build your profile, tailor CVs and interview practice to you, and show you what is and is not working in your job search. We do not sell your information or use it for advertising.</p>

        <h2>Who processes it</h2>
        <ul className="dots">
          <li><span className="strong">Supabase</span> stores your account and data, in London.</li>
          <li><span className="strong">Amazon Web Services (Bedrock)</span> runs the AI model that writes text for you, in the United States.</li>
          <li><span className="strong">ElevenLabs</span> runs voice calls and turns them into text.</li>
          <li><span className="strong">Reed</span> supplies job adverts. We send it job titles and locations from your target roles, never your name or anything else about you.</li>
        </ul>

        <h2>Visa and sponsorship facts</h2>
        <p>Salary figures and the register of licensed sponsors come from gov.uk and are shown with the date we last checked them. They are facts to check for yourself, not immigration advice. Contains public sector information licensed under the Open Government Licence v3.0.</p>

        <h2>How long we keep it</h2>
        <p>Until you delete your account.</p>

        <h2>Your choices</h2>
        <p>You can delete your account and everything in it at any time from the Account page. You can also remove individual achievements, jobs and applications.</p>

        {contact && <><h2>Contact</h2><p>Questions about your information: <a href={`mailto:${contact}`}>{contact}</a></p></>}
      </main>
    </div>
  )
}
