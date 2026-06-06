function fmtGB(value) {
  return typeof value === 'number' ? `${value.toFixed(1)} GB` : 'unknown'
}

export default function ColdTransferPauseNotice({ status }) {
  if (!status?.cold_transfers_paused) return null

  const used = fmtGB(status.nas_used_gb)
  const limit = fmtGB(status.cold_transfer_min_nas_used_gb)
  const reason = status.cold_transfer_pause_reason
    ?? 'Cold transfers are paused because NAS usage is below the configured safe limit.'

  return (
    <div className="relative overflow-hidden rounded-lg border border-amber-500/30 bg-gradient-to-r from-amber-950/40 via-gray-900/90 to-gray-900 px-4 py-3 shadow-lg shadow-amber-950/10">
      <div className="absolute inset-y-0 left-0 w-1 bg-amber-400" />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 pl-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-300">
            Cold transfers waiting
          </div>
          <p className="mt-1 text-sm text-amber-100/90">{reason}</p>
          <p className="mt-1 text-xs text-gray-500">
            Active freezes finish safely. Reheats can continue while queued cold transfers wait.
          </p>
        </div>
        <div className="shrink-0 rounded-md border border-amber-400/20 bg-black/25 px-3 py-2 text-right">
          <div className="text-[10px] uppercase tracking-[0.18em] text-gray-500">NAS used</div>
          <div className="font-mono text-sm text-amber-200">{used}</div>
          <div className="text-[11px] text-gray-500">limit {limit}</div>
        </div>
      </div>
    </div>
  )
}
