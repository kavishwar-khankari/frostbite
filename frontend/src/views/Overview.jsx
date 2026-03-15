import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getDashboard, getScoreHistory, getSettings, triggerLibrarySync, triggerScoringRun, triggerTdarrSync } from '../api/client'
import StatCard from '../components/StatCard'
import TransferRow from '../components/TransferRow'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend,
} from 'recharts'

function fmtGB(bytes) {
  return `${(bytes / 1e9).toFixed(1)} GB`
}

function fmtDateTime(iso) {
  const d = new Date(iso)
  const mo = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${mo}/${day} ${h}:${m}`
}

const CHART_STYLE = {
  contentStyle: { backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#9ca3af' },
}

export default function Overview() {
  const qc = useQueryClient()
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    // Poll faster when transfers are active so progress bars update smoothly
    refetchInterval: (query) =>
      (query.state.data?.active_transfers?.length ?? 0) > 0 ? 3_000 : 15_000,
  })
  const { data: appSettings } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    refetchInterval: 60_000,
  })

  const { data: history = [] } = useQuery({
    queryKey: ['scoreHistory', 30],
    queryFn: () => getScoreHistory(30),
    refetchInterval: 60_000,
  })

  const syncMut = useMutation({
    mutationFn: triggerLibrarySync,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['dashboard'] }), 3000),
  })
  const scoreMut = useMutation({
    mutationFn: triggerScoringRun,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['dashboard'] }), 20_000),
  })
  const tdarrSyncMut = useMutation({
    mutationFn: triggerTdarrSync,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['dashboard'] }), 15_000),
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

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Overview</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live storage snapshot</p>
        </div>
        <div className="flex gap-2">
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
          sub={stats?.nas_free_gb != null ? `${stats.nas_free_gb.toFixed(1)} GB free` : ''}
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
        <div className="text-sm font-medium text-gray-300">Storage Usage</div>
        {lastSnap && (
          <>
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>NAS used</span>
                <span>{fmtGB(lastSnap.nas_used_bytes ?? 0)}</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-orange-500 rounded-full" style={{ width: '100%' }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Cloud used</span>
                <span>{fmtGB(lastSnap.cloud_used_bytes ?? 0)}</span>
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
          stats.active_transfers.map(t => <TransferRow key={t.id} transfer={t} />)
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
          {stats.queued_transfer_list.map(t => <TransferRow key={t.id} transfer={t} />)}
        </div>
      )}
    </div>
  )
}
