import { useState, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getTransfers, getWorkerStatus,
  pauseAllTransfers, resumeTransfers,
  cancelTransfer, bulkCancelTransfers, bulkBumpTransfers,
} from '../api/client'
import TransferRow from '../components/TransferRow'

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_TABS = ['all', 'active', 'queued', 'completed', 'failed']

function FilterBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded text-xs transition-colors ${
        active
          ? 'bg-frost-600/30 text-frost-300 border border-frost-600/50'
          : 'text-gray-500 hover:text-gray-300 border border-transparent'
      }`}
    >
      {children}
    </button>
  )
}

const PAGE_SIZE = 200

export default function Transfers() {
  const [tab, setTab] = useState('all')
  const [search, setSearch] = useState('')
  const [dirFilter, setDirFilter] = useState('')
  const [triggerFilter, setTriggerFilter] = useState('')
  const [sort, setSort] = useState('priority')
  const [order, setOrder] = useState('desc')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState(new Set())
  const qc = useQueryClient()

  // Reset to page 0 when any filter/sort changes
  const resetOffset = () => setOffset(0)

  const switchTab = (t) => {
    setTab(t)
    setOffset(0)
    if (t === 'completed') {
      setSort('completed_at')
      setOrder('desc')
    } else if (tab === 'completed') {
      setSort('priority')
      setOrder('desc')
    }
  }

  const queryParams = {
    ...(tab !== 'all' && { status: tab }),
    ...(dirFilter && { direction: dirFilter }),
    ...(triggerFilter && { trigger: triggerFilter }),
    sort,
    order,
    limit: PAGE_SIZE,
    offset,
  }

  const { data: page = { items: [], total: 0 }, isLoading } = useQuery({
    queryKey: ['transfers', queryParams],
    queryFn: () => getTransfers(queryParams),
    refetchInterval: 5_000,
  })

  const transfers = page.items ?? []
  const totalCount = page.total ?? 0

  const { data: workerStatus } = useQuery({
    queryKey: ['worker-status'],
    queryFn: getWorkerStatus,
    refetchInterval: 5_000,
  })
  const paused = workerStatus?.paused ?? false

  // Client-side search filters within the current page
  const displayed = useMemo(() => {
    if (!search.trim()) return transfers
    const q = search.toLowerCase()
    return transfers.filter(t => {
      const title = (t.item_title ?? t.id).toLowerCase()
      const series = (t.item_series_name ?? '').toLowerCase()
      return title.includes(q) || series.includes(q)
    })
  }, [transfers, search])

  // byStatus counts are from the current page only — used for active/completed tabs
  // For queued tab, totalCount is the real number from the backend
  const byStatus = transfers.reduce((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1
    return acc
  }, {})

  const allIds = transfers.map(t => t.id)
  const allSelected = allIds.length > 0 && allIds.every(id => selected.has(id))
  const someSelected = selected.size > 0

  const toggleSelect = (id) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const toggleAll = () => {
    if (allSelected) {
      setSelected(prev => { const n = new Set(prev); allIds.forEach(id => n.delete(id)); return n })
    } else {
      setSelected(prev => new Set([...prev, ...allIds]))
    }
  }

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['transfers'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    setSelected(new Set())
  }

  const pauseAll = useMutation({ mutationFn: pauseAllTransfers, onSuccess: invalidate })
  const resume   = useMutation({ mutationFn: resumeTransfers,   onSuccess: invalidate })
  const bulkCancel = useMutation({
    mutationFn: () => bulkCancelTransfers([...selected]),
    onSuccess: invalidate,
  })
  const bulkBump = useMutation({
    mutationFn: () => bulkBumpTransfers([...selected]),
    onSuccess: invalidate,
  })

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">Transfers</h1>
          {paused && (
            <span className="text-xs font-medium uppercase tracking-wide text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded">
              Paused
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">
          {totalCount > PAGE_SIZE
            ? `${offset + 1}–${Math.min(offset + transfers.length, totalCount)} of ${totalCount.toLocaleString()}`
            : `${totalCount.toLocaleString()} total`}
        </span>
          {paused ? (
            <button className="btn-success text-xs py-1 px-3" onClick={() => resume.mutate()} disabled={resume.isPending}>
              Resume
            </button>
          ) : (
            <button className="btn-danger text-xs py-1 px-3" onClick={() => pauseAll.mutate()} disabled={pauseAll.isPending}>
              Pause All
            </button>
          )}
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <input
          type="text"
          placeholder="Search by title…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="input text-sm py-1.5 w-56"
        />

        {/* Direction */}
        <div className="flex items-center gap-1 border border-gray-700 rounded px-1 py-0.5">
          <FilterBtn active={dirFilter === ''} onClick={() => setDirFilter('')}>All</FilterBtn>
          <FilterBtn active={dirFilter === 'freeze'} onClick={() => setDirFilter('freeze')}>❄️ Freeze</FilterBtn>
          <FilterBtn active={dirFilter === 'reheat'} onClick={() => setDirFilter('reheat')}>🔥 Reheat</FilterBtn>
        </div>

        {/* Trigger */}
        <div className="flex items-center gap-1 border border-gray-700 rounded px-1 py-0.5">
          <FilterBtn active={triggerFilter === ''} onClick={() => setTriggerFilter('')}>Any trigger</FilterBtn>
          <FilterBtn active={triggerFilter === 'auto_score'} onClick={() => setTriggerFilter('auto_score')}>auto</FilterBtn>
          <FilterBtn active={triggerFilter === 'manual'} onClick={() => setTriggerFilter('manual')}>manual</FilterBtn>
          <FilterBtn active={triggerFilter === 'space_pressure'} onClick={() => setTriggerFilter('space_pressure')}>emergency</FilterBtn>
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1 ml-auto">
          <select
            value={sort}
            onChange={e => setSort(e.target.value)}
            className="input text-xs py-1"
          >
            <option value="queued_at">Queued time</option>
            <option value="priority">Priority</option>
            <option value="completed_at">Completed time</option>
          </select>
          <button
            onClick={() => setOrder(o => o === 'desc' ? 'asc' : 'desc')}
            className="btn-ghost text-xs py-1 px-2"
            title={order === 'desc' ? 'Newest first' : 'Oldest first'}
          >
            {order === 'desc' ? '↓' : '↑'}
          </button>
        </div>
      </div>

      {/* Bulk action bar — only when something is selected */}
      {someSelected && (
        <div className="flex items-center gap-3 bg-frost-900/20 border border-frost-700/30 rounded-lg px-4 py-2">
          <span className="text-sm text-frost-300">{selected.size} selected</span>
          <button
            className="btn-danger text-xs py-1 px-3"
            onClick={() => bulkCancel.mutate()}
            disabled={bulkCancel.isPending}
          >
            Cancel selected
          </button>
          <button
            className="btn-success text-xs py-1 px-3"
            onClick={() => bulkBump.mutate()}
            disabled={bulkBump.isPending}
          >
            Bump to front
          </button>
          <button
            className="text-xs text-gray-500 hover:text-gray-300 ml-auto"
            onClick={() => setSelected(new Set())}
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Status tabs */}
      <div className="flex gap-1 border-b border-gray-800 pb-0">
        {STATUS_TABS.map(t => (
          <button
            key={t}
            className={`px-3 py-2 text-sm capitalize border-b-2 transition-colors -mb-px ${
              tab === t
                ? 'border-frost-500 text-frost-300 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
            onClick={() => switchTab(t)}
          >
            {t}
            {/* For the active tab show real total, otherwise page counts */}
            {t === tab && totalCount > 0 && (
              <span className="ml-1.5 text-xs text-gray-600">({totalCount.toLocaleString()})</span>
            )}
          </button>
        ))}
      </div>

      {/* Transfers list */}
      <div className="card p-0 divide-y divide-gray-800/50">
        {/* Select-all header */}
        {transfers.length > 0 && (
          <div className="px-4 py-2 flex items-center gap-3 bg-gray-800/20">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              className="rounded bg-gray-700 border-gray-600"
            />
            <span className="text-xs text-gray-500">
              {allSelected ? 'Deselect all' : `Select all ${transfers.length}`}
            </span>
          </div>
        )}

        {isLoading && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">Loading…</div>
        )}
        {!isLoading && transfers.length === 0 && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">
            No transfers match your filters
          </div>
        )}
        {transfers.map(t => (
          <div key={t.id} className={`px-4 transition-colors ${selected.has(t.id) ? 'bg-frost-900/10' : ''}`}>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(t.id)}
                onChange={() => toggleSelect(t.id)}
                className="rounded bg-gray-700 border-gray-600 shrink-0"
              />
              <div className="flex-1 min-w-0">
                <TransferRow transfer={t} />
              </div>
            </div>
            <div className="flex gap-4 pb-2 pl-6 text-xs text-gray-600">
              <span>Queued: {fmtTime(t.queued_at)}</span>
              {t.started_at && <span>Started: {fmtTime(t.started_at)}</span>}
              {t.completed_at && <span>Completed: {fmtTime(t.completed_at)}</span>}
              <span className="text-gray-700">priority {t.priority}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Pagination */}
      {totalCount > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>{offset + 1}–{Math.min(offset + transfers.length, totalCount)} of {totalCount.toLocaleString()}</span>
          <div className="flex gap-2">
            <button
              className="btn-ghost text-xs py-1 px-3"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              ← Prev
            </button>
            <button
              className="btn-ghost text-xs py-1 px-3"
              disabled={offset + PAGE_SIZE >= totalCount}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
