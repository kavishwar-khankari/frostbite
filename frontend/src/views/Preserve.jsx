import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getDeletionCandidates, scanDeletionCandidates, approveDeletionCandidate,
  protectCandidateItem, protectCandidateSeries,
  getDeletionExceptions, getDeletionStats, removeDeletionException,
} from '../api/client'
import { formatBytes } from '../utils/format'

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function StatCard({ label, value, icon, color }) {
  return (
    <div className="card flex items-center gap-3 px-5 py-4">
      <span className={`text-2xl ${color}`}>{icon}</span>
      <div>
        <div className="text-2xl font-bold text-white tabular-nums">{value}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  )
}

function CandidateRow({ c, onApprove, onProtectItem, onProtectSeries, isMutating }) {
  return (
    <tr className="border-b border-gray-800/30 hover:bg-gray-800/30 group">
      <td className="px-4 py-2">
        <div className="text-sm text-white truncate max-w-xs">
          {c.season_number != null && c.episode_number != null
            ? `S${String(c.season_number).padStart(2, '0')}E${String(c.episode_number).padStart(2, '0')} — ${c.title}`
            : c.title}
        </div>
      </td>
      <td className="px-4 py-2 text-center">
        <span className={`text-sm tabular-nums font-medium ${
          c.temperature <= 1 ? 'text-red-400' : c.temperature <= 3 ? 'text-yellow-400' : 'text-gray-300'
        }`}>{c.temperature.toFixed(1)}</span>
      </td>
      <td className="px-4 py-2 text-right text-xs text-gray-400 tabular-nums">{formatBytes(c.file_size_bytes, 2)}</td>
      <td className="px-4 py-2 text-right text-xs text-gray-500">{fmtDate(c.created_at)}</td>
      <td className="px-4 py-2 text-right w-48">
        <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            className="btn bg-red-900/40 hover:bg-red-800/60 text-red-300 text-xs py-0.5 px-2"
            onClick={() => onApprove(c)} disabled={isMutating}
            title="Delete this file from cloud storage"
          >Delete</button>
          <button
            className="btn bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300 text-xs py-0.5 px-2"
            onClick={() => onProtectItem(c.id)} disabled={isMutating}
            title="Protect this item from deletion"
          >🛡</button>
          {c.series_id && (
            <button
              className="btn bg-frost-900/40 hover:bg-frost-800/60 text-frost-300 text-xs py-0.5 px-2"
              onClick={() => onProtectSeries(c.id)} disabled={isMutating}
              title="Protect the entire series from deletion"
            >📚</button>
          )}
        </div>
      </td>
    </tr>
  )
}

function SeriesGroup({ seriesId, seriesName, candidates, onApprove, onProtectItem, onProtectSeries, onDeleteAll, isMutating }) {
  const [open, setOpen] = useState(false)
  const totalSize = candidates.reduce((s, c) => s + c.file_size_bytes, 0)
  const avgTemp = candidates.reduce((s, c) => s + c.temperature, 0) / candidates.length

  return (
    <div className="border-b border-gray-800/40 group/series last:border-0">
      <div className="flex items-center hover:bg-gray-800/20 cursor-pointer" onClick={() => setOpen(v => !v)}>
        <div className="flex-1 flex items-center gap-3 px-4 py-3 min-w-0">
          <span className="text-gray-500 text-xs w-3 shrink-0">{open ? '▾' : '▸'}</span>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-white text-sm truncate">{seriesName}</div>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-xs text-gray-500">{candidates.length} episodes</span>
              <span className="text-xs text-yellow-400">avg {avgTemp.toFixed(1)}°</span>
            </div>
          </div>
          <div className="flex items-center gap-4 shrink-0">
            <span className="text-xs text-gray-500 w-16 text-right tabular-nums">{formatBytes(totalSize)}</span>
          </div>
        </div>
        <div className="flex gap-1 pr-3 opacity-0 group-hover/series:opacity-100 transition-opacity shrink-0">
          <button
            className="btn bg-red-900/40 hover:bg-red-800/60 text-red-300 text-xs py-0.5 px-2"
            onClick={e => { e.stopPropagation(); onDeleteAll() }}
            disabled={isMutating}
            title="Delete all candidates in this series from cloud storage"
          >🗑 Delete all</button>
          <button
            className="btn bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300 text-xs py-0.5 px-2"
            onClick={e => { e.stopPropagation(); onProtectSeries(candidates[0].id) }}
            disabled={isMutating}
            title="Protect the entire series from deletion"
          >📚 Protect series</button>
        </div>
      </div>
      {open && (
        <div className="bg-gray-950/30">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800/30 text-xs text-gray-600 uppercase tracking-wider">
                <th className="px-4 py-1.5 text-left">Episode</th>
                <th className="px-4 py-1.5 text-center">Temp</th>
                <th className="px-4 py-1.5 text-right">Size</th>
                <th className="px-4 py-1.5 text-right">Created</th>
                <th className="px-4 py-1.5 text-right w-48">Actions</th>
              </tr>
            </thead>
            <tbody>
              {candidates
                .sort((a, b) => {
                  if (a.season_number !== b.season_number) return (a.season_number || 0) - (b.season_number || 0)
                  return (a.episode_number || 0) - (b.episode_number || 0)
                })
                .map(c => (
                  <CandidateRow
                    key={c.id}
                    c={c}
                    onApprove={onApprove}
                    onProtectItem={onProtectItem}
                    onProtectSeries={onProtectSeries}
                    isMutating={isMutating}
                  />
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Preserve() {
  const qc = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [search, setSearch] = useState('')
  const [excSearch, setExcSearch] = useState('')
  const [excScope, setExcScope] = useState('')
  const [page, setPage] = useState(0)
  const [excPage, setExcPage] = useState(0)
  const [viewMode, setViewMode] = useState('grouped')
  const [groupSort, setGroupSort] = useState('count')
  const [groupSortDir, setGroupSortDir] = useState('desc')
  const LIMIT = viewMode === 'grouped' ? 2000 : 100

  const { data: stats } = useQuery({
    queryKey: ['deletionStats'],
    queryFn: getDeletionStats,
    refetchInterval: 30_000,
  })

  const { data: candidatesPage, isFetching: candFetching } = useQuery({
    queryKey: ['deletionCandidates', status, search, viewMode, page],
    queryFn: () => getDeletionCandidates({ status, search: search || undefined, limit: LIMIT, offset: page * LIMIT }),
    keepPreviousData: true,
  })

  const { data: exceptionsPage, isFetching: excFetching } = useQuery({
    queryKey: ['deletionExceptions', excScope, excSearch, excPage],
    queryFn: () => getDeletionExceptions({ scope: excScope || undefined, search: excSearch || undefined, limit: LIMIT, offset: excPage * LIMIT }),
    keepPreviousData: true,
  })

  const scanMut = useMutation({
    mutationFn: scanDeletionCandidates,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deletionCandidates'] })
      qc.invalidateQueries({ queryKey: ['deletionStats'] })
    },
  })

  const approveMut = useMutation({
    mutationFn: approveDeletionCandidate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deletionCandidates'] })
      qc.invalidateQueries({ queryKey: ['deletionStats'] })
      qc.invalidateQueries({ queryKey: ['items'] })
      qc.invalidateQueries({ queryKey: ['series'] })
    },
  })

  const protectItemMut = useMutation({
    mutationFn: protectCandidateItem,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deletionCandidates'] })
      qc.invalidateQueries({ queryKey: ['deletionStats'] })
      qc.invalidateQueries({ queryKey: ['deletionExceptions'] })
      qc.invalidateQueries({ queryKey: ['items'] })
    },
  })

  const protectSeriesMut = useMutation({
    mutationFn: protectCandidateSeries,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deletionCandidates'] })
      qc.invalidateQueries({ queryKey: ['deletionStats'] })
      qc.invalidateQueries({ queryKey: ['deletionExceptions'] })
      qc.invalidateQueries({ queryKey: ['series'] })
    },
  })

  const removeMut = useMutation({
    mutationFn: removeDeletionException,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deletionExceptions'] })
      qc.invalidateQueries({ queryKey: ['deletionStats'] })
      qc.invalidateQueries({ queryKey: ['items'] })
      qc.invalidateQueries({ queryKey: ['series'] })
    },
  })

  const candidates = candidatesPage?.items ?? []
  const sortedCandidates = useMemo(() => {
    if (viewMode !== 'flat') return candidates
    const sorted = [...candidates]
    sorted.sort((a, b) => {
      let va, vb
      switch (groupSort) {
        case 'name':
          va = (a.title || '').toLowerCase()
          vb = (b.title || '').toLowerCase()
          return groupSortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
        case 'temp':
          va = a.temperature; vb = b.temperature
          break
        case 'size':
          va = a.file_size_bytes; vb = b.file_size_bytes
          break
        default: return 0
      }
      return groupSortDir === 'asc' ? va - vb : vb - va
    })
    return sorted
  }, [candidates, viewMode, groupSort, groupSortDir])
  const exceptions = exceptionsPage?.items ?? []
  const candTotal = candidatesPage?.total ?? 0
  const excTotal = exceptionsPage?.total ?? 0
  const candPages = Math.ceil(candTotal / LIMIT)
  const excPages = Math.ceil(excTotal / LIMIT)

  const handleApprove = (c) => {
    if (!window.confirm(
      `Delete "${c.title}" from cloud storage? This cannot be undone by Frostbite.`
    )) return
    approveMut.mutate(c.id)
  }

  const handleDeleteAll = (candidates) => {
    const totalSize = candidates.reduce((s, c) => s + c.file_size_bytes, 0)
    if (!window.confirm(
      `Delete ${candidates.length} episodes from cloud storage? Total: ${formatBytes(totalSize)}. This cannot be undone by Frostbite.`
    )) return
    for (const c of candidates) approveMut.mutate(c.id)
  }

  const handleRemoveException = (e) => {
    if (!window.confirm(
      `Remove deletion exception for "${e.title || e.jellyfin_id || e.series_id}"? The item may become a deletion candidate again on the next scan.`
    )) return
    removeMut.mutate(e.id)
  }

  const isMutating = approveMut.isPending || protectItemMut.isPending || protectSeriesMut.isPending

  const { seriesGroups, standaloneItems } = useMemo(() => {
    const groups = {}
    const standalone = []
    for (const c of candidates) {
      if (c.series_id) {
        if (!groups[c.series_id]) {
          groups[c.series_id] = { seriesId: c.series_id, seriesName: c.series_name || c.series_id, candidates: [] }
        }
        groups[c.series_id].candidates.push(c)
      } else {
        standalone.push(c)
      }
    }

    const resolveValue = (g) => {
      const totalSize = g.candidates.reduce((s, c) => s + c.file_size_bytes, 0)
      const avgTemp = g.candidates.reduce((s, c) => s + c.temperature, 0) / g.candidates.length
      switch (groupSort) {
        case 'count': return g.candidates.length
        case 'name': return (g.seriesName || '').toLowerCase()
        case 'temp': return avgTemp
        case 'size': return totalSize
        default: return g.candidates.length
      }
    }

    const sortedGroups = Object.values(groups).sort((a, b) => {
      const va = resolveValue(a)
      const vb = resolveValue(b)
      if (typeof va === 'string') return groupSortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
      return groupSortDir === 'asc' ? va - vb : vb - va
    })

    return {
      seriesGroups: sortedGroups,
      standaloneItems: standalone,
    }
  }, [candidates, groupSort, groupSortDir])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Preserve</h1>
          <p className="text-sm text-gray-500 mt-0.5">Review low-temperature cold media before deletion and manage deletion exceptions.</p>
        </div>
        <button
          className="btn bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300"
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
        >
          {scanMut.isPending ? '⟳ Scanning…' : '🔍 Scan Now'}
        </button>
      </div>

      {scanMut.data && (
        <div className="card border-emerald-800/40 bg-emerald-950/20">
          <div className="text-sm text-emerald-300">
            Scan complete: {scanMut.data.created} new approvals, {scanMut.data.superseded} stale candidates superseded.
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Pending approvals" value={stats?.pending_candidates ?? 0} icon="⏳" color="text-yellow-400" />
        <StatCard label="Failed deletions" value={stats?.failed_candidates ?? 0} icon="⚠️" color="text-red-400" />
        <StatCard label="Protected media" value={stats?.item_exceptions ?? 0} icon="🛡️" color="text-emerald-400" />
        <StatCard label="Protected series" value={stats?.series_exceptions ?? 0} icon="📚" color="text-emerald-400" />
        <StatCard label="Deleted by Frostbite" value={stats?.deleted_candidates ?? 0} icon="🗑️" color="text-gray-500" />
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800 flex items-center gap-3">
          <h2 className="text-sm font-semibold text-white">Deletion Approvals</h2>
          <div className="flex gap-1 ml-auto">
            <button
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                viewMode === 'grouped'
                  ? 'bg-frost-600/30 text-frost-300 border border-frost-600/40'
                  : 'bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-gray-700/40'
              }`}
              onClick={() => { setViewMode('grouped'); setPage(0) }}
            >📺 Grouped</button>
            <button
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                viewMode === 'flat'
                  ? 'bg-frost-600/30 text-frost-300 border border-frost-600/40'
                  : 'bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-gray-700/40'
              }`}
              onClick={() => { setViewMode('flat'); setPage(0) }}
            >📋 List</button>
            <span className="w-2" />
            {['pending', 'failed', 'deleted', 'protected', 'superseded'].map(s => (
              <button
                key={s}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  status === s
                    ? 'bg-frost-600/30 text-frost-300 border border-frost-600/40'
                    : 'bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-gray-700/40'
                }`}
                onClick={() => { setStatus(s); setPage(0) }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="px-4 py-2 border-b border-gray-800/50 flex items-center gap-4">
          <input
            className="input w-full max-w-xs"
            placeholder="Search candidates…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0) }}
          />
          <div className="flex items-center gap-2 ml-auto">
            <select
              className="select w-28 text-xs"
              value={groupSort}
              onChange={e => setGroupSort(e.target.value)}
            >
              <option value="count">Episodes</option>
              <option value="name">Name</option>
              <option value="temp">Avg Temp</option>
              <option value="size">Size</option>
            </select>
            <button
              className="btn-ghost text-xs px-2"
              onClick={() => setGroupSortDir(d => d === 'desc' ? 'asc' : 'desc')}
              title={groupSortDir === 'desc' ? 'Descending' : 'Ascending'}
            >
              {groupSortDir === 'desc' ? '↓' : '↑'}
            </button>
          </div>
          <span className="text-xs text-gray-600">{candTotal.toLocaleString()} total</span>
        </div>

        {viewMode === 'flat' && (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-2.5 text-left">Title</th>
                <th className="px-4 py-2.5 text-center">Temperature</th>
                <th className="px-4 py-2.5 text-right">Size</th>
                <th className="px-4 py-2.5 text-left">Status</th>
                <th className="px-4 py-2.5 text-right">Created</th>
                <th className="px-4 py-2.5 text-right w-56">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedCandidates.map(c => (
                <tr key={c.id} className="border-b border-gray-800/50 hover:bg-gray-800/20 group">
                  <td className="px-4 py-2.5 max-w-xs">
                    <div className="font-medium text-sm text-white truncate">{c.title}</div>
                    <div className="text-xs text-gray-600 truncate">
                      {c.series_name && `${c.series_name} `}
                      {c.season_number != null && c.episode_number != null
                        ? `S${String(c.season_number).padStart(2, '0')}E${String(c.episode_number).padStart(2, '0')}`
                        : c.item_type}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <span className={`text-sm tabular-nums font-medium ${
                      c.temperature <= 1 ? 'text-red-400' : c.temperature <= 3 ? 'text-yellow-400' : 'text-gray-300'
                    }`}>{c.temperature.toFixed(1)}</span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-gray-400 tabular-nums">{formatBytes(c.file_size_bytes, 2)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${
                      c.status === 'deleted' ? 'bg-red-950/50 text-red-300 border border-red-900/60' :
                      c.status === 'protected' ? 'bg-emerald-950/50 text-emerald-300 border border-emerald-900/60' :
                      c.status === 'failed' ? 'bg-red-950/40 text-red-400 border border-red-800/60' :
                      c.status === 'superseded' ? 'bg-gray-900/50 text-gray-500 border border-gray-800/60' :
                      'bg-yellow-950/40 text-yellow-300 border border-yellow-800/60'
                    }`}>{c.status}</span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-gray-500">{fmtDate(c.created_at)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button className="btn bg-red-900/40 hover:bg-red-800/60 text-red-300 text-xs py-0.5 px-2" onClick={() => handleApprove(c)} disabled={isMutating}>Delete</button>
                      <button className="btn bg-emerald-900/40 hover:bg-emerald-800/60 text-emerald-300 text-xs py-0.5 px-2" onClick={() => protectItemMut.mutate(c.id)} disabled={isMutating}>🛡</button>
                      {c.series_id && <button className="btn bg-frost-900/40 hover:bg-frost-800/60 text-frost-300 text-xs py-0.5 px-2" onClick={() => protectSeriesMut.mutate(c.id)} disabled={isMutating}>📚</button>}
                    </div>
                  </td>
                </tr>
              ))}
              {sortedCandidates.length === 0 && !candFetching && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-600 text-sm">No candidates found</td></tr>
              )}
            </tbody>
          </table>
        )}

        {viewMode === 'grouped' && (
          <div>
            {standaloneItems.length > 0 && (
              <div>
                <div className="px-4 py-2 border-b border-gray-800/50 text-xs text-gray-500 uppercase tracking-wider">Standalone (no series)</div>
                <table className="w-full text-sm">
                  <tbody>
                    {standaloneItems.map(c => (
                      <CandidateRow
                        key={c.id}
                        c={c}
                        onApprove={handleApprove}
                        onProtectItem={protectItemMut.mutate}
                        onProtectSeries={protectSeriesMut.mutate}
                        isMutating={isMutating}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {seriesGroups.map(g => (
              <SeriesGroup
                key={g.seriesId}
                seriesId={g.seriesId}
                seriesName={g.seriesName}
                candidates={g.candidates}
                onApprove={handleApprove}
                onProtectItem={protectItemMut.mutate}
                onProtectSeries={protectSeriesMut.mutate}
                onDeleteAll={() => handleDeleteAll(g.candidates)}
                isMutating={isMutating}
              />
            ))}

            {seriesGroups.length === 0 && standaloneItems.length === 0 && !candFetching && (
              <div className="px-4 py-8 text-center text-gray-600 text-sm">No candidates found</div>
            )}
          </div>
        )}

        {candPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-800 text-xs text-gray-500">
            <span>{candTotal.toLocaleString()} items</span>
            <div className="flex gap-1 items-center">
              <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>Prev</button>
              <span className="px-2">{page + 1} / {candPages}</span>
              <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setPage(p => Math.min(candPages - 1, p + 1))} disabled={page >= candPages - 1}>Next</button>
            </div>
          </div>
        )}
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800 flex items-center gap-3">
          <h2 className="text-sm font-semibold text-white">Deletion Exceptions</h2>
          <div className="flex gap-1 ml-auto">
            {['', 'item', 'series'].map(s => (
              <button
                key={s}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  excScope === s
                    ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-600/40'
                    : 'bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-gray-700/40'
                }`}
                onClick={() => { setExcScope(s); setExcPage(0) }}
              >
                {s || 'all'}
              </button>
            ))}
          </div>
        </div>
        <div className="px-4 py-2 border-b border-gray-800/50">
          <input
            className="input w-full max-w-xs"
            placeholder="Search exceptions…"
            value={excSearch}
            onChange={e => { setExcSearch(e.target.value); setExcPage(0) }}
          />
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-2.5 text-left">Scope</th>
              <th className="px-4 py-2.5 text-left">Title</th>
              <th className="px-4 py-2.5 text-left">Reason</th>
              <th className="px-4 py-2.5 text-right">Created</th>
              <th className="px-4 py-2.5 text-right w-24">Actions</th>
            </tr>
          </thead>
          <tbody>
            {exceptions.map(e => (
              <tr key={e.id} className="border-b border-gray-800/50 hover:bg-gray-800/20 group">
                <td className="px-4 py-2.5">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${
                    e.scope === 'series'
                      ? 'bg-frost-950/50 text-frost-300 border border-frost-800/60'
                      : 'bg-emerald-950/50 text-emerald-300 border border-emerald-900/60'
                  }`}>{e.scope}</span>
                </td>
                <td className="px-4 py-2.5 max-w-xs">
                  <div className="text-sm text-white truncate">{e.title || e.jellyfin_id || e.series_id}</div>
                </td>
                <td className="px-4 py-2.5 text-sm text-gray-400 italic">{e.reason || '—'}</td>
                <td className="px-4 py-2.5 text-right text-xs text-gray-500">{fmtDate(e.created_at)}</td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    className="btn btn-danger text-xs py-0.5 px-2 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => handleRemoveException(e)}
                    disabled={removeMut.isPending}
                  >Remove</button>
                </td>
              </tr>
            ))}
            {exceptions.length === 0 && !excFetching && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-600 text-sm">No exceptions found</td></tr>
            )}
          </tbody>
        </table>
        {excPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-800 text-xs text-gray-500">
            <span>{excTotal.toLocaleString()} items</span>
            <div className="flex gap-1 items-center">
              <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setExcPage(p => Math.max(0, p - 1))} disabled={excPage === 0}>Prev</button>
              <span className="px-2">{excPage + 1} / {excPages}</span>
              <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setExcPage(p => Math.min(excPages - 1, p + 1))} disabled={excPage >= excPages - 1}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
