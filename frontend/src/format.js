// Formatting helpers (prices, dates).
//
// Prices are Indian rupees, as the API sends them: Indian digit grouping
// (₹1,23,456), a dot before paise (₹12.95), and paise only when there are some.

const whole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const withPaise = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function money(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const r = Math.round(Number(v) * 100) / 100
  const abs = Math.abs(r)
  const text = Number.isInteger(abs) ? whole.format(abs) : withPaise.format(abs)
  return `${r < 0 ? '−' : ''}₹${text}`
}

// 1326.6 -> { int: "1,326", paise: "60" } for the big-price layout (₹1,326.60)
export function priceParts(v) {
  const r = Math.round(Number(v || 0) * 100) / 100
  const [int, paise = '00'] = withPaise.format(r).split('.')
  return { int, paise: paise === '00' ? '' : paise }
}

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { weekday: 'short' })
const DAY_MONTH = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

// "Wed, 11 Nov": today + the product's median real delivery time
export function deliveryDate(days) {
  const d = new Date()
  d.setDate(d.getDate() + Math.max(2, days || 7))
  return `${WEEKDAY.format(d)}, ${DAY_MONTH.format(d)}`
}

export function dateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function date(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h} h ago`
  return date(iso)
}

export const shortId = (id) => (id || '').replace(/^o_(app_)?/, '').slice(-6).toUpperCase()
export const titleCase = (s = '') => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
export const initials = (name = '') => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || 'K'
