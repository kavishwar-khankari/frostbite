const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
}

// ── Dashboard ──────────────────────────────────────────────────────────────
export const getDashboard = () => req('/dashboard')

// ── Items ─────────────────────────────────────────────────────────────────
export const getItems = (params = {}) => {
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  ).toString()
  return req(`/items${qs ? `?${qs}` : ''}`)
}

export const overrideTemperature = (jellyfin_id, temperature) =>
  req(`/items/${jellyfin_id}/temperature`, {
    method: 'PATCH',
    body: JSON.stringify({ temperature }),
  })

// ── Series ────────────────────────────────────────────────────────────────
export const getSeries = (search) =>
  req(`/series${search ? `?search=${encodeURIComponent(search)}` : ''}`)

// ── Transfers ────────────────────────────────────────────────────────────
export const getTransfers = (status) =>
  req(`/transfers${status ? `?status=${status}` : ''}`)

export const cancelTransfer = (id) =>
  req(`/transfers/${id}/cancel`, { method: 'POST' })

export const retryTransfer = (id) =>
  req(`/transfers/${id}/retry`, { method: 'POST' })

// ── Controls ──────────────────────────────────────────────────────────────
export const manualFreeze = (jellyfin_id) =>
  req('/freeze', { method: 'POST', body: JSON.stringify({ jellyfin_id }) })

export const manualReheat = (jellyfin_id) =>
  req('/reheat', { method: 'POST', body: JSON.stringify({ jellyfin_id }) })

export const bulkFreeze = (jellyfin_ids) =>
  req('/bulk-freeze', { method: 'POST', body: JSON.stringify({ jellyfin_ids }) })

export const bulkReheat = (jellyfin_ids) =>
  req('/bulk-reheat', { method: 'POST', body: JSON.stringify({ jellyfin_ids }) })

export const triggerLibrarySync = () =>
  req('/sync/library', { method: 'POST' })

// ── Score history ────────────────────────────────────────────────────────
export const getScoreHistory = (days = 30) =>
  req(`/score-history?days=${days}`)

// ── Settings ─────────────────────────────────────────────────────────────
export const getSettings = () => req('/settings')

export const updateSetting = (key, value) =>
  req('/settings', { method: 'PUT', body: JSON.stringify({ key, value }) })
