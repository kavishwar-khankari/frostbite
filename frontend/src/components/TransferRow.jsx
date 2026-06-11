import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelTransfer, retryTransfer } from '../api/client'
import ProgressBar from './ProgressBar'
import { formatBytes, formatDateTime } from '../utils/format'

function fmtSpeed(bps) {
  if (!bps) return ''
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} MB/s`
  return `${(bps / 1e3).toFixed(0)} KB/s`
}

function fmtEta(s) {
  if (!s) return ''
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${(s / 3600).toFixed(1)}h`
}

const STATUS_COLOR = {
  active:    'text-frost-400',
  queued:    'text-yellow-400',
  completed: 'text-emerald-400',
  failed:    'text-red-400',
  cancelled: 'text-gray-500',
  retried:   'text-amber-400',
}

function queuedWaitReason(transfer, workerStatus) {
  if (transfer.status !== 'queued') return null
  if (workerStatus?.paused) return 'Waiting: transfer worker is paused.'

  if (transfer.direction === 'freeze') {
    if (transfer.item_upload_blocked) return 'Blocked: filename is too long for cloud storage.'
    if (transfer.trigger === 'auto_score' && transfer.item_prefetch_protected_until) {
      return `Protected from auto-freeze until watched or ${formatDateTime(transfer.item_prefetch_protected_until)}.`
    }
    const blocker = workerStatus?.freeze_start_blocker
    if (blocker === 'freeze_concurrency') return 'Waiting: max active freezes reached.'
    if (blocker === 'freeze_window') return 'Waiting: outside freeze window.'
    if (blocker === 'nas_usage_gate') return 'Waiting: NAS used is below the cold-transfer safe limit.'
    if (blocker === 'global_pause') return 'Waiting: transfer worker is paused.'
    return 'Waiting behind higher-priority freeze transfers.'
  }

  if (transfer.direction === 'reheat') {
    const blocker = workerStatus?.reheat_start_blocker
    if (blocker === 'reheat_concurrency') return 'Waiting: max active reheats reached.'
    if (blocker === 'global_pause') return 'Waiting: transfer worker is paused.'
    return 'Waiting behind higher-priority reheat transfers.'
  }

  return null
}

export default function TransferRow({ transfer, workerStatus }) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['transfers'], exact: false })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const cancel = useMutation({
    mutationFn: () => cancelTransfer(transfer.id),
    onSuccess: invalidate,
  })
  const retry = useMutation({
    mutationFn: () => retryTransfer(transfer.id),
    onSuccess: invalidate,
  })

  const canCancel = ['queued', 'active'].includes(transfer.status)
  const canRetry  = ['failed', 'cancelled'].includes(transfer.status)

  const title = transfer.item_title ?? transfer.id
  const isEpisode = transfer.item_type === 'episode'
  const waitReason = queuedWaitReason(transfer, workerStatus)

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-800/60 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white truncate">
          {isEpisode && transfer.item_series_name ? (
            <>
              <span className="text-gray-400">{transfer.item_series_name}</span>
              {transfer.item_season_number != null && (
                <><span className="text-gray-600"> — </span><span className="text-gray-500">Season {transfer.item_season_number}</span></>
              )}
              <span className="text-gray-600"> — </span>{title}
            </>
          ) : title}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={`text-xs font-medium uppercase tracking-wide ${STATUS_COLOR[transfer.status] || 'text-gray-400'}`}>
            {transfer.status}
          </span>
          <span className="text-xs text-gray-500">
            {transfer.direction === 'freeze' ? '❄️ → Cold' : '🔥 → Hot'}
          </span>
          <span className="text-xs text-gray-600">
            {transfer.trigger}
          </span>
        </div>
        {transfer.status === 'active' && transfer.bytes_total > 0 && (
          <div className="space-y-0.5">
            <ProgressBar value={transfer.bytes_transferred} max={transfer.bytes_total} />
            <div className="flex justify-between text-xs text-gray-500">
              <span>{formatBytes(transfer.bytes_transferred)} / {formatBytes(transfer.bytes_total)}</span>
              <span>{fmtSpeed(transfer.speed_bps)} {fmtEta(transfer.eta_seconds) && `· ETA ${fmtEta(transfer.eta_seconds)}`}</span>
            </div>
          </div>
        )}
        {waitReason && (
          <div className="mt-1 text-xs text-amber-400/90 truncate" title={waitReason}>
            {waitReason}
          </div>
        )}
        {transfer.error_message && (
          <div className="text-xs text-red-400 mt-1 truncate">{transfer.error_message}</div>
        )}
      </div>
      <div className="flex gap-1 shrink-0">
        {canCancel && (
          <button
            className="btn-danger text-xs py-1 px-2"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
          >
            Cancel
          </button>
        )}
        {canRetry && (
          <button
            className="btn-success text-xs py-1 px-2"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
