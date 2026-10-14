import { accessToken, refreshToken } from './supabase'

let signedOut = () => {}
// App registers what to do when the server no longer accepts the session
export const onSignedOut = (fn) => { signedOut = fn }

function send(path, method, body, token) {
  const headers = {}
  const file = body instanceof Blob // a file travels as the raw body, exactly as it is
  if (body) headers['Content-Type'] = file ? 'application/octet-stream' : 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(path, { method, headers, body: !body || file ? body || undefined : JSON.stringify(body) })
}

// One call with the login token. The token may simply have expired: refresh once and retry before giving up
async function request(path, method, body) {
  let r = await send(path, method, body, await accessToken())
  if (r.status === 401) {
    const fresh = await refreshToken()
    if (fresh) r = await send(path, method, body, fresh)
    if (r.status === 401) signedOut()
  }
  return r
}

function message(data, status) {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return d[0].msg.replace(/^Value error, /, '')
  return `Request failed (${status})`
}

function failure(data, status) {
  const err = new Error(message(data, status))
  err.status = status
  return err
}

export async function api(path, { method = 'GET', body } = {}) {
  const r = await request(path, method, body)
  const data = r.status === 204 ? null : await r.json().catch(() => ({}))
  if (!r.ok) throw failure(data, r.status)
  return data
}

export const post = (path, body = {}) => api(path, { method: 'POST', body })
export const patch = (path, body = {}) => api(path, { method: 'PATCH', body })
export const put = (path, body = {}) => api(path, { method: 'PUT', body })
export const del = (path) => api(path, { method: 'DELETE' })
export const upload = (path, file) => api(path, { method: 'POST', body: file })

// A file the server makes for the signed-in user. A plain link cannot carry the login token, so the
// file is fetched like any other call and handed to the browser to save under the name the server gave
export async function download(path) {
  const r = await request(path, 'GET')
  if (!r.ok) throw failure(await r.json().catch(() => ({})), r.status)
  const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || 'download'
  const url = URL.createObjectURL(await r.blob())
  const link = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
  return name
}
