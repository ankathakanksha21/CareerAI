import { Component, useCallback, useEffect, useState } from 'react'
import { LogOut } from 'lucide-react'
import { api, onSignedOut } from './api'
import { getSupabase } from './supabase'
import { Avatar, Brand, ErrorRetry, NAV, Spinner } from './ui'
import Landing from './pages/Landing'
import Auth from './pages/Auth'
import Privacy from './pages/Privacy'
import Onboarding from './pages/Onboarding'
import Home from './pages/Home'
import Profile from './pages/Profile'
import Pathways from './pages/Pathways'
import Jobs from './pages/Jobs'
import Resume from './pages/Resume'
import Interview from './pages/Interview'
import Applications from './pages/Applications'
import Networking from './pages/Networking'
import Peers from './pages/Peers'
import Journal from './pages/Journal'
import Account from './pages/Account'

const PAGES = { home: Home, profile: Profile, pathways: Pathways, jobs: Jobs, resume: Resume, interview: Interview, applications: Applications, networking: Networking, peers: Peers, journal: Journal, account: Account }

function readHash() {
  const [page, tab] = window.location.hash.slice(1).split('/')
  return { page: page || '', tab: tab || null }
}

const isReset = () => new URLSearchParams(window.location.search).has('reset')

// A page that throws shows a message instead of blanking the whole app
class PageBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <ErrorRetry error={new Error('Something went wrong on this page.')} onRetry={() => this.setState({ error: null })} />
    return this.props.children
  }
}

export default function App() {
  const [session, setSession] = useState(undefined) // undefined while loading, null when signed out
  const [s, setS] = useState(null)
  const [error, setError] = useState(null)
  const [nav, setNav] = useState(readHash)
  const [focus, setFocus] = useState({}) // cross-page hand-offs, e.g. which job to tailor
  const [toast, setToast] = useState(null)
  const [reset, setReset] = useState(isReset)
  const userId = session?.user?.id

  useEffect(() => {
    let unsubscribe = () => {}
    getSupabase().then((sb) => {
      onSignedOut(() => sb.auth.signOut({ scope: 'local' }))
      sb.auth.getSession().then(({ data }) => setSession(data.session))
      const { data } = sb.auth.onAuthStateChange((_event, next) => setSession(next))
      unsubscribe = () => data.subscription.unsubscribe()
    }).catch(() => setError("We can't reach the server. Try again in a minute."))
    const onHash = () => setNav(readHash())
    window.addEventListener('hashchange', onHash)
    return () => { unsubscribe(); window.removeEventListener('hashchange', onHash) }
  }, [])

  const refresh = useCallback(() => api('/api/state').then((d) => { setError(null); setS(d) }).catch((e) => {
    if (e.status !== 401) setError(e.message)
  }), [])
  useEffect(() => {
    if (userId) refresh()
    else setS(null)
  }, [userId, refresh])

  const go = (page, tab = null, extra = {}) => {
    setFocus(extra)
    window.location.hash = tab ? `${page}/${tab}` : page
    window.scrollTo(0, 0)
  }
  const notify = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3200)
  }
  const signOut = async () => {
    const sb = await getSupabase()
    await sb.auth.signOut()
    window.location.hash = ''
  }
  const finishReset = () => {
    window.history.replaceState(null, '', window.location.pathname)
    setReset(false)
    go('home')
  }

  const toastEl = toast && <div className="toast" role="status">{toast}</div>
  if (session === undefined && !error) return <div className="main app-loading"><Spinner /></div>
  if (nav.page === 'privacy') return <Privacy go={go} signedIn={!!session} />

  if (!session) {
    if (error) return <div className="main"><p className="error">{error}</p></div>
    if (nav.page === 'auth') return <Auth mode={nav.tab || 'signin'} go={go} />
    return <Landing go={go} signedIn={false} />
  }

  if (reset) return <Auth mode="newpassword" go={go} onDone={finishReset} />
  if (error && !s) return <div className="main"><ErrorRetry error={new Error(error)} onRetry={refresh} /></div>
  if (!s) return <div className="main app-loading"><Spinner /></div>

  const props = { s, refresh, go, tab: nav.tab, focus, notify, session, signOut }
  if (nav.page === 'landing') return <><Landing go={go} signedIn />{toastEl}</>
  if (!s.details_complete || nav.page === 'onboarding') return <><Onboarding {...props} />{toastEl}</>

  const page = PAGES[nav.page] ? nav.page : 'home'
  const Page = PAGES[page]
  return (
    <div className="shell">
      <aside className="side">
        <Brand onClick={() => go('home')} />
        <nav className="nav-group" aria-label="Your search">
          {NAV.filter((item) => item.key !== 'jobs' || s.config.jobs).map(({ key, label, icon: Icon }) => (
            <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => go(key)} aria-current={page === key ? 'page' : undefined}>
              <Icon size={18} strokeWidth={1.9} />
              {label}
              {key === 'applications' && s.stats.findings.length > 0 && <span className="count" title="Things to fix">{s.stats.findings.length}</span>}
              {key === 'jobs' && s.jobs.new > 0 && <span className="count" title="New matching jobs">{s.jobs.new}</span>}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <button className="me" onClick={() => go('account')} aria-label="Your account" title="Your account">
            <Avatar name={s.profile.full_name} size="sm" />
            <span className="name">{s.profile.full_name}</span>
          </button>
          <button className="icon-btn calm side-signout" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut size={17} aria-hidden="true" /></button>
        </div>
      </aside>
      <main className="main">
        {/* page-enter: the page's cards fade up in sequence when it opens (index.css, design board D18) */}
        <PageBoundary key={page}><div className="page-enter"><Page {...props} /></div></PageBoundary>
      </main>
      {toastEl}
    </div>
  )
}
