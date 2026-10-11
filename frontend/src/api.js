import { accessToken, refreshToken } from './supabase'

let signedOut = () => {}
// App registers what to do when the server no longer accepts the session
export const onSignedOut = (fn) => { signedOut = fn }

function send(path, method, body, token) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined })
}

function message(data, status) {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg.replace(/^Value error, /, '')
  return `Request failed (${status})`
}

export async function api(path, { method = 'GET', body } = {}) {
  let r = await send(path, method, body, await accessToken())
  if (r.status === 401) {
    // the token may simply have expired: refresh once and retry before giving up
    const fresh = await refreshToken()
    if (fresh) r = await send(path, method, body, fresh)
    if (r.status === 401) signedOut()
  }
  const data = r.status === 204 ? null : await r.json().catch(() => ({}))
  if (!r.ok) {
    const err = new Error(message(data, r.status))
    err.status = r.status
    throw err
  }
  return data
}

export const post = (path, body = {}) => api(path, { method: 'POST', body })
export const patch = (path, body = {}) => api(path, { method: 'PATCH', body })
export const put = (path, body = {}) => api(path, { method: 'PUT', body })
export const del = (path) => api(path, { method: 'DELETE' })
