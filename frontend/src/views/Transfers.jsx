import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTransfers } from '../api/client'
import TransferRow from '../components/TransferRow'

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const TABS = ['all', 'active', 'queued', 'completed', 'failed']

export default function Transfers() {
  const [tab, setTab] = useState('all')

  const { data: transfers = [], isLoading } = useQuery({
    queryKey: ['transfers', tab],
    queryFn: () => getTransfers(tab === 'all' ? undefined : tab),
    refetchInterval: 5_000,
  })

  const byStatus = transfers.reduce((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Transfers</h1>
        <span className="text-sm text-gray-500">{transfers.length} shown</span>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 border-b border-gray-800 pb-0">
        {TABS.map(t => (
          <button
            key={t}
            className={`px-3 py-2 text-sm capitalize border-b-2 transition-colors -mb-px ${
              tab === t
                ? 'border-frost-500 text-frost-300 font-medium'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
            onClick={() => setTab(t)}
          >
            {t}
            {byStatus[t] && (
              <span className="ml-1.5 text-xs text-gray-600">({byStatus[t]})</span>
            )}
          </button>
        ))}
      </div>

      {/* Transfers list */}
      <div className="card p-0 divide-y divide-gray-800/50">
        {isLoading && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">Loading…</div>
        )}
        {!isLoading && transfers.length === 0 && (
          <div className="px-4 py-8 text-center text-gray-600 text-sm">
            No {tab === 'all' ? '' : tab} transfers
          </div>
        )}
        {transfers.map(t => (
          <div key={t.id} className="px-4">
            <TransferRow transfer={t} />
            <div className="flex gap-4 pb-2 text-xs text-gray-600">
              <span>Queued: {fmtTime(t.queued_at)}</span>
              {t.started_at && <span>Started: {fmtTime(t.started_at)}</span>}
              {t.completed_at && <span>Completed: {fmtTime(t.completed_at)}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
