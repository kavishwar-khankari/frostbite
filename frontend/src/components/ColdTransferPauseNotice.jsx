import { formatBytes, formatGib } from '../utils/format'

function formatDecimalGb(bytes) {
  return typeof bytes === 'number' ? `${(bytes / 1e9).toFixed(1)} decimal GB` : 'unknown'
}

function blockerLabel(status) {
  const blocker = status?.freeze_start_blocker
  if (blocker === 'none') return 'Ready to start queued freezes.'
  if (blocker === 'no_queued_freezes') return 'No queued freezes waiting.'
  if (status?.freeze_start_blocker_reason) return status.freeze_start_blocker_reason
  return status?.cold_transfer_pause_reason ?? 'Cold-transfer gate state is unavailable.'
}

export default function ColdTransferPauseNotice({ status }) {
  if (!status) return null
  const queuedFreezes = status.queued_freezes ?? 0

  const blocker = status.freeze_start_blocker
  const blocked = queuedFreezes > 0 && blocker && !['none', 'no_queued_freezes'].includes(blocker)
  const ready = queuedFreezes > 0 && blocker === 'none'
  const accent = blocked ? 'amber' : ready ? 'emerald' : 'frost'
  const accentClasses = {
    amber: 'border-amber-500/30 bg-gradient-to-r from-amber-950/40 via-gray-900/90 to-gray-900 shadow-amber-950/10 text-amber-100/90',
    emerald: 'border-emerald-500/30 bg-gradient-to-r from-emerald-950/30 via-gray-900/90 to-gray-900 shadow-emerald-950/10 text-emerald-100/90',
    frost: 'border-frost-500/20 bg-gradient-to-r from-frost-900/20 via-gray-900/90 to-gray-900 shadow-frost-900/10 text-gray-300',
  }[accent]
  const rail = blocked ? 'bg-amber-400' : ready ? 'bg-emerald-400' : 'bg-frost-400'
  const label = blocked ? 'Cold transfers waiting' : ready ? 'Cold transfers ready' : 'Cold transfer gate'
  const used = status.nas_used_bytes != null ? formatBytes(status.nas_used_bytes) : formatGib(status.nas_used_gib)
  const limit = status.cold_transfer_min_nas_used_bytes != null
    ? formatBytes(status.cold_transfer_min_nas_used_bytes)
    : formatGib(status.cold_transfer_min_nas_used_gib ?? status.cold_transfer_min_nas_used_gb)
  const windowText = `${String(status.freeze_window_start ?? 0).padStart(2, '0')}:00-${String(status.freeze_window_end ?? 0).padStart(2, '0')}:00 IST`

  return (
    <div className={`relative overflow-hidden rounded-lg border px-4 py-3 shadow-lg ${accentClasses}`}>
      <div className={`absolute inset-y-0 left-0 w-1 ${rail}`} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 pl-2">
          <div className={`text-[11px] font-semibold uppercase tracking-[0.2em] ${blocked ? 'text-amber-300' : ready ? 'text-emerald-300' : 'text-frost-300'}`}>
            {label}
          </div>
          <p className="mt-1 text-sm">{blockerLabel(status)}</p>
          <p className="mt-1 text-xs text-gray-500 tabular-nums">
            Freeze window {windowText} · {status.freeze_window_active ? 'active now' : 'inactive now'} ·
            {' '}queue {queuedFreezes} freeze / {status.queued_reheats ?? 0} reheat
          </p>
        </div>
        <div className="grid shrink-0 grid-cols-2 gap-2 text-right sm:min-w-[360px]">
          <div className="rounded-md border border-white/10 bg-black/25 px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.18em] text-gray-500">NAS used</div>
            <div className="font-mono text-sm text-white">{used}</div>
            <div className="text-[11px] text-gray-500">{formatDecimalGb(status.nas_used_bytes)}</div>
          </div>
          <div className="rounded-md border border-white/10 bg-black/25 px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.18em] text-gray-500">Start limit</div>
            <div className="font-mono text-sm text-white">{limit}</div>
            <div className="text-[11px] text-gray-500">{formatDecimalGb(status.cold_transfer_min_nas_used_bytes)}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
