const BYTES_PER_KIB = 1024
const BYTES_PER_MIB = 1024 ** 2
const BYTES_PER_GIB = 1024 ** 3
const BYTES_PER_TIB = 1024 ** 4

export function formatBytes(bytes, precision = 1) {
  if (typeof bytes !== 'number' || Number.isNaN(bytes)) return 'unknown'
  const abs = Math.abs(bytes)
  if (abs >= BYTES_PER_TIB) return `${(bytes / BYTES_PER_TIB).toFixed(2)} TiB`
  if (abs >= BYTES_PER_GIB) return `${(bytes / BYTES_PER_GIB).toFixed(precision)} GiB`
  if (abs >= BYTES_PER_MIB) return `${(bytes / BYTES_PER_MIB).toFixed(precision)} MiB`
  if (abs >= BYTES_PER_KIB) return `${(bytes / BYTES_PER_KIB).toFixed(0)} KiB`
  return `${bytes} B`
}

export function formatGib(value, precision = 1) {
  return typeof value === 'number' && !Number.isNaN(value) ? `${value.toFixed(precision)} GiB` : 'unknown'
}

export function bytesToGib(bytes) {
  return typeof bytes === 'number' ? bytes / BYTES_PER_GIB : null
}

export function formatDateTime(iso) {
  if (!iso) return 'unknown'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
