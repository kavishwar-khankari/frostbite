import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getDashboard, getScoreHistory, getSettings, getWorkerStatus, triggerLibrarySync, triggerScoringRun, triggerTdarrSync, importPlaybackHistory } from '../api/client'
import ColdTransferPauseNotice from '../components/ColdTransferPauseNotice'
import StatCard from '../components/StatCard'
import TransferRow from '../components/TransferRow'
import { formatBytes } from '../utils/format'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend,
} from 'recharts'

function fmtDateTime(iso) {
  const d = new Date(iso)
  const mo = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${mo}/${day} ${h}:${m}`
}

function freezeWaitReason(status) {
  const blocker = status?.freeze_start_blocker
  if (blocker === 'none') return 'ready'
  if (blocker === 'global_pause') return 'worker paused'
  if (blocker === 'freeze_concurrency') return 'freeze slots full'
  if (blocker === 'freeze_window') return 'outside freeze window'
  if (blocker === 'nas_usage_gate') return 'NAS gate'
  if (blocker === 'no_queued_freezes') return 'no queued freezes'
  return 'queued'
}

function NextFreezeOrder({ transfers = [], workerStatus, candidateCount = 0, uploadBlockedCount = 0 }) {
  const wait = freezeWaitReason(workerStatus)
  const emptyMessage = uploadBlockedCount > 0
    ? `${candidateCount} freeze candidate${candidateCount === 1 ? '' : 's'} below the temperature threshold; ${uploadBlockedCount} blocked because the filename exceeds OpenDrive's 120-character safe limit.`
    : 'No freeze candidates are currently queued.'
  return (
    <div className="card overflow-hidden">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-gray-300">Upcoming Freezes</div>
          <div className="text-xs text-gray-600">Actual queue order: priority, then queued time</div>
        </div>
        <span className="rounded border border-frost-500/20 bg-frost-900/20 px-2 py-1 text-xs text-frost-300">
          {wait}
        </span>
      </div>
      {transfers.length > 0 ? (
        <div className="divide-y divide-gray-800/60">
          {transfers.slice(0, 10).map((t, i) => (
            <div key={t.id} className="grid grid-cols-[2rem_1fr_auto_auto_auto] items-center gap-3 py-2 text-sm">
              <div className="font-mono text-xs text-gray-600">#{i + 1}</div>
              <div className="min-w-0">
                <div className="truncate text-gray-200">{t.item_title ?? t.id}</div>
                {t.item_series_name && <div className="truncate text-xs text-gray-600">{t.item_series_name}</div>}
              </div>
              <div className="text-right font-mono text-xs text-cyan-300">{t.item_temperature?.toFixed(1) ?? '—'}°</div>
              <div className="text-right font-mono text-xs text-gray-500">p{t.priority}</div>
              <div className="text-right text-xs text-gray-500">{formatBytes(t.item_file_size_bytes, 1)}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className={`rounded-md border px-3 py-3 text-sm ${uploadBlockedCount > 0 ? 'border-amber-500/20 bg-amber-950/20 text-amber-200/80' : 'border-gray-800 bg-gray-950/30 text-gray-500'}`}>
          {emptyMessage}
        </div>
      )}
    </div>
  )
}

const CHART_STYLE = {
  contentStyle: { backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#9ca3af' },
}

function Toast({ message, type, onClose }) {
  const bg = type === 'error' ? 'bg-red-600/90 border-red-500' : 'bg-emerald-600/90 border-emerald-500'
  return (
    <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-lg border text-sm text-white shadow-lg ${bg} animate-fade-in`}>
      <div className="flex items-center gap-3">
        <span>{message}</span>
        <button onClick={onClose} className="text-white/70 hover:text-white">✕</button>
      </div>
    </div>
  )
}

export default function Overview() {
  const qc = useQueryClient()
  const [toast, setToast] = useState(null)

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 15000)
  }

  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    // Poll faster when transfers are active so progress bars update smoothly
    refetchInterval: (query) =>
      (query.state.data?.active_transfers?.length ?? 0) > 0 ? 2_000 : 10_000,
  })
  const { data: appSettings } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    refetchInterval: 60_000,
  })
  const { data: workerStatus } = useQuery({
    queryKey: ['worker-status'],
    queryFn: getWorkerStatus,
    refetchInterval: 10_000,
  })

  const { data: history = [] } = useQuery({
    queryKey: ['scoreHistory', 30],
    queryFn: () => getScoreHistory(30),
    refetchInterval: 60_000,
  })

  const onDone = (label) => (data) => {
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    if (data?.status === 'failed') {
      showToast(`${label} failed: ${data.error}`, 'error')
    } else {
      const extra = data?.total != null ? ` (${data.new ?? 0} new, ${data.updated ?? 0} updated)` : ''
      showToast(`${label} completed${extra}`)
    }
  }
  const onErr = (label) => (err) => showToast(`${label} failed: ${err.message}`, 'error')

  const syncMut = useMutation({
    mutationFn: triggerLibrarySync,
    onSuccess: onDone('Library sync'),
    onError: onErr('Library sync'),
  })
  const scoreMut = useMutation({
    mutationFn: triggerScoringRun,
    onSuccess: onDone('Scoring sweep'),
    onError: onErr('Scoring sweep'),
  })
  const tdarrSyncMut = useMutation({
    mutationFn: triggerTdarrSync,
    onSuccess: onDone('Tdarr sync'),
    onError: onErr('Tdarr sync'),
  })
  const importHistoryMut = useMutation({
    mutationFn: importPlaybackHistory,
    onSuccess: onDone('Playback import'),
    onError: onErr('Playback import'),
  })

  const chartData = history.map(h => ({
    date: fmtDateTime(h.recorded_at),
    hot: h.hot_items,
    cold: h.cold_items,
    avg_temp: parseFloat(h.avg_temperature.toFixed(1)),
  }))

  if (isLoading) {
    return <div className="flex items-center justify-center h-full text-gray-500">Loading…</div>
  }

  const hotPct = stats?.total_items > 0
    ? ((stats.hot_items / stats.total_items) * 100).toFixed(1)
    : '0.0'

  const lastSnap = history[history.length - 1]
  const nasUsedBytes = stats?.nas_used_bytes ?? lastSnap?.nas_used_bytes ?? null
  const nasAvailableBytes = stats?.nas_available_bytes ?? null
  const nasTotalBytes = stats?.nas_total_bytes ?? null
  const cloudUsedBytes = stats?.cloud_used_bytes ?? lastSnap?.cloud_used_bytes ?? null
  const nasPct = nasTotalBytes && nasUsedBytes != null
    ? Math.min(100, Math.max(0, (nasUsedBytes / nasTotalBytes) * 100))
    : 100

  return (
    <div className="p-6 space-y-6">
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Overview</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live storage snapshot</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => importHistoryMut.mutate()} disabled={importHistoryMut.isPending}
            title="Re-import all play history from Jellyfin Playback Reporting plugin (resets sync cursor)">
            {importHistoryMut.isPending ? '⟳ Importing…' : '📥 Reimport History'}
          </button>
          <button className="btn-ghost" onClick={() => tdarrSyncMut.mutate()} disabled={tdarrSyncMut.isPending}
            title="Pull latest eligibility data from Tdarr">
            {tdarrSyncMut.isPending ? '⟳ Syncing…' : '⟳ Tdarr Sync'}
          </button>
          <button className="btn-ghost" onClick={() => scoreMut.mutate()} disabled={scoreMut.isPending}
            title="Runs the temperature scoring sweep immediately">
            {scoreMut.isPending ? '⟳ Scoring…' : '🌡 Score Now'}
          </button>
          <button className="btn-primary" onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
            {syncMut.isPending ? '⟳ Syncing…' : '⟳ Sync Library'}
          </button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Items"
          value={stats?.total_items?.toLocaleString() ?? '—'}
          sub={`${hotPct}% on NAS`}
          accent="blue"
        />
        <StatCard
          label="Hot (NAS)"
          value={stats?.hot_items?.toLocaleString() ?? '—'}
          sub={nasAvailableBytes != null ? `${formatBytes(nasAvailableBytes)} free` : ''}
          accent="orange"
        />
        <StatCard
          label="Cold (Cloud)"
          value={stats?.cold_items?.toLocaleString() ?? '—'}
          accent="blue"
        />
        <StatCard
          label="Avg Temperature"
          value={stats?.avg_temperature?.toFixed(1) ?? '—'}
          sub="0 = coldest · 100 = hottest"
          accent="purple"
        />
      </div>

      {/* Secondary stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          label="Tdarr Eligible"
          value={stats?.tdarr_eligible_count?.toLocaleString() ?? '—'}
          sub="files ready for scoring/freezing"
          accent="green"
        />
        <StatCard
          label="Transferring"
          value={stats?.transferring_items?.toLocaleString() ?? '—'}
          sub={`${stats?.queued_transfers ?? 0} queued`}
          accent="purple"
        />
      </div>

      {/* Storage bars */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-gray-300">Live Storage Usage</div>
          <div className="text-xs text-gray-600">
            {stats?.storage_checked_at ? `checked ${fmtDateTime(stats.storage_checked_at)}` : lastSnap ? 'historical fallback' : ''}
          </div>
        </div>
        {(nasUsedBytes != null || cloudUsedBytes != null) && (
          <>
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>NAS used</span>
                <span>{formatBytes(nasUsedBytes)}</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-orange-500 rounded-full" style={{ width: `${nasPct}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Cloud used {stats?.cloud_usage_source && <span className="text-gray-700">({stats.cloud_usage_source})</span>}</span>
                <span>{formatBytes(cloudUsedBytes)}</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-frost-500 rounded-full" style={{ width: '100%' }} />
              </div>
            </div>
          </>
        )}
      </div>

      {/* Score history chart */}
      {chartData.length > 0 && (
        <div className="card">
          <div className="text-sm font-medium text-gray-300 mb-4">30-Day Tier History</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
              <Tooltip {...CHART_STYLE} />
              <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="hot" stroke="#f97316" dot={false} strokeWidth={1.5} name="Hot" />
              <Line type="monotone" dataKey="cold" stroke="#38bdf8" dot={false} strokeWidth={1.5} name="Cold" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <ColdTransferPauseNotice status={workerStatus} />
      <NextFreezeOrder
        transfers={stats?.queued_freeze_list ?? []}
        workerStatus={workerStatus}
        candidateCount={stats?.freeze_candidate_count ?? 0}
        uploadBlockedCount={stats?.upload_blocked_freeze_candidates ?? 0}
      />

      {/* Active transfers */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium text-gray-300">Active Transfers</div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            {appSettings && (
              <>
                <span>
                  Freeze: {stats?.active_transfers?.filter(t => t.direction === 'freeze').length ?? 0}
                  /{appSettings.max_concurrent_freezes}
                </span>
                <span>
                  Reheat: {stats?.active_transfers?.filter(t => t.direction === 'reheat').length ?? 0}
                  /{appSettings.max_concurrent_reheats}
                </span>
              </>
            )}
          </div>
        </div>
        {stats?.active_transfers?.length > 0 ? (
          stats.active_transfers.map(t => (
            <TransferRow key={t.id} transfer={t} workerStatus={workerStatus} />
          ))
        ) : (
          <div className="text-sm text-gray-600 py-2">No active transfers</div>
        )}
      </div>

      {/* Upcoming (queued) transfers */}
      {stats?.queued_transfer_list?.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-medium text-gray-300">Upcoming Transfers</div>
            <span className="text-xs text-gray-500">{stats.queued_transfers} in queue</span>
          </div>
          {stats.queued_transfer_list.map(t => (
            <TransferRow key={t.id} transfer={t} workerStatus={workerStatus} />
          ))}
        </div>
      )}
    </div>
  )
}
