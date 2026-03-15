import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelTransfer, retryTransfer } from '../api/client'
import ProgressBar from './ProgressBar'

function fmtBytes(b) {
  if (!b) return '—'
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`
  return `${(b / 1e3).toFixed(0)} KB`
}

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
}

export default function TransferRow({ transfer }) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['transfers'] })
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

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-800/60 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-white truncate">
          {isEpisode && transfer.item_series_name
            ? <><span className="text-gray-400">{transfer.item_series_name}</span> — {title}</>
            : title
          }
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
              <span>{fmtBytes(transfer.bytes_transferred)} / {fmtBytes(transfer.bytes_total)}</span>
              <span>{fmtSpeed(transfer.speed_bps)} {fmtEta(transfer.eta_seconds) && `· ETA ${fmtEta(transfer.eta_seconds)}`}</span>
            </div>
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
