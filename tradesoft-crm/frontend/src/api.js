// Tiny fetch wrapper for the standalone TradeSoft CRM backend.
const BASE = '/api'

async function get(path, params) {
  const url = new URL(BASE + path, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== undefined && v !== null) url.searchParams.set(k, v)
  })
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

export const api = {
  stats: () => get('/stats'),
  list: (entity, params) => get(`/${entity}`, params),
  detail: (entity, id) => get(`/${entity}/${id}`),
}

// ---- formatting helpers ----
export const fmtMoney = (v, ccy = 'USD') => {
  const n = Number(v || 0)
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: ccy && ccy.length === 3 ? ccy : 'USD',
    maximumFractionDigits: 2,
  }).format(n)
}
export const fmtNum = (v) => new Intl.NumberFormat('en-US').format(Number(v || 0))
export const fmtDate = (v) => {
  if (!v) return '—'
  const s = String(v).replace('T', ' ').slice(0, 19)
  return s || '—'
}
export const fmtDay = (v) => (v ? String(v).slice(0, 10) : '—')
