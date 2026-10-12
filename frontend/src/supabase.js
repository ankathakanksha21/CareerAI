import { createClient } from '@supabase/supabase-js'

/*
  Supabase is used for one thing in the browser: signing in and holding the session.
  All data goes through our own /api. The project URL and publishable key (both safe
  to expose) come from the backend, so there is a single place where settings live.
*/
let configPromise = null
let clientPromise = null

export function getConfig() {
  configPromise ||= fetch('/api/config').then((r) => {
    if (!r.ok) throw new Error(`Config request failed (${r.status})`)
    return r.json()
  })
  return configPromise
}

export function getSupabase() {
  clientPromise ||= getConfig().then((c) => createClient(c.supabase_url, c.supabase_publishable_key, {
    // PKCE returns its code in the query string, so it never collides with our #hash routes
    auth: { flowType: 'pkce', detectSessionInUrl: true, persistSession: true, autoRefreshToken: true },
  }))
  return clientPromise
}

export async function accessToken() {
  const sb = await getSupabase()
  const { data } = await sb.auth.getSession()
  return data.session?.access_token || null
}

export async function refreshToken() {
  const sb = await getSupabase()
  const { data, error } = await sb.auth.refreshSession()
  return error ? null : data.session?.access_token || null
}
