// Words and small rules for prep packs, shared by the Interview page and the application panel

export const INTERVIEW_TYPE_LABEL = { phone: 'Phone', video: 'Video', in_person: 'In person' }
export const SECTION_LABEL = {
  what_they_do: 'What they do', size: 'Size and age', values: 'Values, in their words',
  products: 'Products and projects', news: 'News, last 12 months', competitors: 'Competitors',
}
export const QUESTION_KIND = { motivation: 'Motivation', role: 'Role knowledge' }
export const PREP_STAGES = new Set(['screening', 'interview']) // an application at these stages has an interview to prepare for

// The pack for a saved job, or for an application: the application's saved job's pack when it has one
export function packFor(s, { jobId, appId }) {
  const app = appId && s.applications.find((a) => a.id === appId)
  const job = jobId || app?.saved_job_id
  return job ? s.prep_packs.find((p) => p.saved_job_id === job) : s.prep_packs.find((p) => p.application_id === appId && !p.saved_job_id)
}

// What a new pack is for, with the employer name to look up
export function targetFor(s, { jobId, appId }) {
  const app = appId && s.applications.find((a) => a.id === appId)
  if (app) return { application_id: app.id, role: app.role, company: app.company }
  const job = s.saved_jobs.find((j) => j.id === jobId)
  return job ? { job_id: job.id, role: job.title, company: job.company } : null
}
