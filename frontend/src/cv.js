// Helpers for a CV document on screen. The server decides every fact and what prints; these only
// mirror how it words dates and the contact line, and work out small edits to send back.

export const SECTION_TITLE = { education: 'Education', work: 'Work experience', projects: 'Projects', skills: 'Skills', additional: 'Additional information' }
export const SKILL_LABEL = { technical: 'Technical', tools: 'Tools', languages: 'Languages' }
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const HOME = new Set(['united kingdom', 'uk', 'u.k.', 'great britain', 'gb', 'england', 'scotland', 'wales', 'northern ireland'])
const JOB_FACTS = ['employer', 'job_title', 'location', 'country', 'start_month', 'end_month', 'is_current', 'employer_context']
const COURSE_FACTS = ['institution', 'qualification', 'subject', 'start_month', 'end_month', 'grade', 'country']

const month = (iso) => (iso ? `${SHORT[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}` : '')

// When a job or course ran, as the files print it. A course with only its end month shows that month
export function cvPeriod(e, course = false) {
  const start = month(e.start_month)
  const end = e.is_current ? 'present' : month(e.end_month)
  if (start) return end ? `${start} to ${end}` : `From ${start}`
  if (e.is_current) return 'Current'
  return end ? (course ? end : `Until ${end}`) : ''
}

export const contactLine = (c) => [c.city, c.phone, c.email, c.linkedin, c.github].filter(Boolean).join(' | ')
export const abroad = (country) => !!country && !HOME.has(country.trim().toLowerCase())
export const joined = (...parts) => parts.filter(Boolean).join(', ')
export const wordCount = (text) => (text || '').trim().split(/\s+/).filter(Boolean).length

// A list with one item moved to another place
export function moved(list, from, to) {
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

// The places of the items that are showing, in order: moving up or down skips anything hidden
export const shownAt = (list) => list.map((_, i) => i).filter((i) => !list[i].hidden)

const entries = (doc) => [...doc.work, ...doc.projects]

// The user's achievements that have no bullet on this CV, hidden or showing
export function unused(doc, achievements) {
  const used = new Set(entries(doc).flatMap((e) => e.bullets.map((b) => b.achievement_id)))
  return achievements.filter((a) => !used.has(a.id))
}

// Put one of the user's achievements on the CV (changes `doc`). One already there but hidden is shown
// again. Otherwise it goes under the job it is linked to, or becomes a project. A job that is not on
// this CV yet is sent with only its id: the server copies its facts from the profile.
export function addAchievement(doc, a) {
  for (const entry of entries(doc)) {
    const bullet = entry.bullets.find((b) => b.achievement_id === a.id)
    if (bullet) {
      bullet.hidden = false
      entry.hidden = false
      return
    }
  }
  const bullet = { text: a.uk_version, achievement_id: a.id, hidden: false }
  if (!a.work_history_id) {
    doc.projects.push({ achievement_id: a.id, title: a.title, link: '', where: '', hidden: false, bullets: [bullet] })
    return
  }
  let job = doc.work.find((w) => w.work_history_id === a.work_history_id)
  if (!job) {
    job = { work_history_id: a.work_history_id, hidden: false, bullets: [] }
    doc.work.push(job)
  }
  job.hidden = false
  job.bullets.push(bullet)
}

const same = (a, b, keys) => keys.every((k) => (a[k] ?? '') === (b[k] ?? ''))

// Whether the profile now says something different from the copy of its facts this CV was built with
export function factsChanged(doc, s) {
  const differs = (stored, records, key, facts) => {
    const byId = Object.fromEntries(records.map((r) => [r.id, r]))
    // an entry just added here has no facts until the server has copied them in: that is not a change to the profile
    return stored.some((e) => facts[0] in e && byId[e[key]] && !same(e, byId[e[key]], facts)) || records.some((r) => !stored.some((e) => e[key] === r.id))
  }
  const p = s.profile
  const now = { name: p.full_name, city: p.city, phone: p.phone, email: p.email, linkedin: p.linkedin_url, github: p.github_username ? `github.com/${p.github_username}` : '' }
  return differs(doc.work, s.work_history, 'work_history_id', JOB_FACTS) || differs(doc.education, s.education, 'education_id', COURSE_FACTS)
    || !same(doc.contact, now, Object.keys(now))
}

// What could come off a CV that runs over two pages, largest saving first
export function trimIdeas(doc) {
  const ideas = []
  const jobs = doc.work.filter((w) => !w.hidden).map((w) => ({ name: w.employer, n: w.bullets.filter((b) => !b.hidden).length }))
  const fullest = jobs.toSorted((a, b) => b.n - a.n)[0]
  if (fullest && fullest.n >= 3) ideas.push(`Hide a bullet under ${fullest.name}: ${fullest.n} are showing.`)
  const projects = doc.projects.filter((p) => !p.hidden && p.bullets.some((b) => !b.hidden)).length
  if (projects >= 2) ideas.push(`Hide a project: ${projects} are showing.`)
  if (jobs.length >= 4) ideas.push(`Hide your oldest or least relevant job: ${jobs.length} are showing.`)
  const words = wordCount(doc.profile)
  if (words > 70) ideas.push(`Shorten your profile: it is ${words} words, and 50 to 70 is enough.`)
  const lines = doc.additional.lines.filter((l) => !l.hidden).length
  if (lines >= 4) ideas.push(`Hide a line under Additional information: ${lines} are showing.`)
  return ideas.length ? ideas : ['Shorten your longest bullets to one line each.']
}

// Achievements linked to neither a job nor a course, apart from GitHub projects: they print under Projects
export const unlinked = (achievements) => achievements.filter((a) => !a.work_history_id && !a.education_id && a.source !== 'github')
