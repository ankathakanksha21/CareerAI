import { useState } from 'react'
import { Check } from 'lucide-react'
import { post } from '../api'
import { Avatar, Brand, ErrorRetry, FamilyCard, useAction } from '../ui'
import DetailsForm from '../components/DetailsForm'
import BackgroundInput from '../components/BackgroundInput'

const STEPS = ['Your details', 'Your background', 'Your profile', 'Target roles']

// Where a user should land: the first step they have not finished
function firstOpenStep(s) {
  if (!s.details_complete) return 0
  if (s.achievements.length === 0) return 1
  if (s.role_families.length === 0) return 2
  return 3
}

function ProfileStep({ s, back, next }) {
  const p = s.profile
  const families = useAction(async () => { await post('/api/ai/families'); await next() })
  return (
    <>
      <div className="ob-title">
        <h1>Your profile</h1>
        <p>Here is what you told us, written the way UK employers read it. Each one shows the words it came from.</p>
      </div>
      <div className="card">
        <div className="profile-head">
          <Avatar name={p.full_name} size="lg" />
          <div>
            <h2 style={{ fontSize: 19 }}>{p.full_name}</h2>
            <p className="muted">{p.course}, {p.university}</p>
            {p.pitch && <p className="pitch">{p.pitch}</p>}
          </div>
        </div>
      </div>
      <div className="section-head section"><h2>{s.achievements.length} {s.achievements.length === 1 ? 'achievement' : 'achievements'} captured</h2></div>
      <div className="stack">
        {s.achievements.map((e) => (
          <div key={e.id} className="card tight">
            <div className="strong">{e.title}</div>
            <p style={{ marginTop: 4 }}>{e.uk_version}</p>
            {e.raw && <p className="said" style={{ marginTop: 4 }}>You said: "{e.raw}"</p>}
            <div className="row" style={{ marginTop: 8 }}>{e.skills.slice(0, 4).map((k) => <span key={k} className="chip">{k}</span>)}</div>
          </div>
        ))}
      </div>
      <ErrorRetry error={families.error} onRetry={families.retry} />
      <div className="ob-actions">
        <button className="btn ghost large" onClick={back}>Add more</button>
        <button className="btn large" disabled={families.loading} onClick={() => (s.role_families.length ? next() : families.run())}>
          {families.loading ? 'Finding roles that fit' : 'Continue'}
        </button>
      </div>
    </>
  )
}

function RolesStep({ s, refresh, go }) {
  const targeted = s.role_families.filter((f) => f.targeted).length
  const toggle = async (f) => { await post(`/api/families/${f.id}/target`, { targeted: !f.targeted }); refresh() }
  return (
    <>
      <div className="ob-title">
        <h1>Your target roles</h1>
        <p>Role families that fit your profile, with what UK employers expect. Pick 3 to 5 to target.</p>
      </div>
      <div className="grid cols-2">
        {s.role_families.map((f) => <FamilyCard key={f.id} f={f} onToggle={toggle} />)}
      </div>
      <div className="ob-actions">
        <span className="small muted" style={{ alignSelf: 'center' }}>{targeted === 0 ? 'Tick at least one role to continue.' : `${targeted} targeted`}</span>
        <button className="btn large" disabled={targeted === 0} onClick={() => go('home')}>Go to my dashboard</button>
      </div>
    </>
  )
}

export default function Onboarding({ s, refresh, go, session }) {
  const [step, setStep] = useState(() => firstOpenStep(s))
  const reachable = firstOpenStep(s)
  const current = Math.min(step, reachable) // never show a step whose earlier steps are unfinished

  return (
    <div>
      <header className="ob-top">
        <Brand onClick={() => (s.details_complete ? go('home') : setStep(0))} />
        <nav className="stepper" aria-label="Onboarding steps">
          {STEPS.map((label, i) => (
            <span key={label} style={{ display: 'contents' }}>
              {i > 0 && <span className="step-line" />}
              <button className={`step ${i === current ? 'active' : i < current ? 'done' : ''}`} disabled={i > reachable} onClick={() => setStep(i)} aria-current={i === current ? 'step' : undefined}>
                <span className="n">{i < current ? <Check size={13} strokeWidth={3} /> : i + 1}</span>
                <span className="label">{label}</span>
              </button>
            </span>
          ))}
        </nav>
        {s.details_complete && <button className="linkish small" onClick={() => go('home')}>I'll do this later</button>}
      </header>
      <main className="ob-body">
        {current === 0 && (
          <>
            <div className="ob-title">
              <h1>Welcome to UK Career Navigator</h1>
              <p>A few exact details first, so everything else fits you.</p>
            </div>
            <div className="card"><DetailsForm profile={s.profile} submitLabel="Continue" onSaved={async () => { await refresh(); setStep(1) }} /></div>
          </>
        )}
        {current === 1 && (
          <>
            <div className="ob-title">
              <h1>Tell us about your background</h1>
              <p>Work, projects, internships, volunteering. We turn it into evidence UK employers understand.</p>
            </div>
            <BackgroundInput s={s} userId={session.user.id} onBuilt={async () => { await refresh(); setStep(2) }} />
            {s.achievements.length > 0 && <div className="ob-actions"><button className="btn ghost large" onClick={() => setStep(2)}>Continue with what I have</button></div>}
          </>
        )}
        {current === 2 && <ProfileStep s={s} back={() => setStep(1)} next={async () => { await refresh(); setStep(3) }} />}
        {current === 3 && <RolesStep s={s} refresh={refresh} go={go} />}
      </main>
    </div>
  )
}
