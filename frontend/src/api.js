// Small fetch wrapper: JSON in/out, bearer token, readable error messages.

const TOKEN_KEY = 'ri_token'

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage blocked: stay logged in for this tab only */ }
}

function messageFrom(body, status) {
  const detail = body && body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join(' › ') : ''
      return field ? `${field}: ${d.msg}` : d.msg
    }).join('; ')
  }
  return status === 503 ? 'The store is temporarily unavailable.' : `Something went wrong (${status}).`
}

export async function api(path, { method = 'GET', body, params } = {}) {
  let url = path
  if (params) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') qs.set(k, v) })
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  const headers = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  let data = null
  try { data = await res.json() } catch { data = null }
  if (!res.ok) {
    const err = new Error(messageFrom(data, res.status))
    err.status = res.status
    throw err
  }
  return data
}
