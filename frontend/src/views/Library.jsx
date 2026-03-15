import { useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getItems, getSeries, bulkFreeze, bulkReheat, manualFreeze, manualReheat, overrideTemperature } from '../api/client'
import TierBadge from '../components/TierBadge'
import TemperatureBar from '../components/TemperatureBar'

function fmtSize(b) {
  if (!b) return '—'
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`
  if (b >= 1e6) return `${(b / 1e6).toFixed(0)} MB`
  return `${(b / 1e3).toFixed(0)} KB`
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

// ── Single item row ─────────────────────────────────────────────────────────
function ItemRow({ item, selected, onSelect }) {
  const qc = useQueryClient()
  const [editTemp, setEditTemp] = useState(false)
  const [tempVal, setTempVal] = useState(item.temperature.toFixed(1))

  const freeze = useMutation({
    mutationFn: () => manualFreeze(item.jellyfin_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['items'] }),
  })
  const reheat = useMutation({
    mutationFn: () => manualReheat(item.jellyfin_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['items'] }),
  })
  const tempMut = useMutation({
    mutationFn: (t) => overrideTemperature(item.jellyfin_id, parseFloat(t)),
    onSuccess: () => { setEditTemp(false); qc.invalidateQueries({ queryKey: ['items'] }) },
  })

  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20 group">
      <td className="px-3 py-2.5 w-8">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onSelect(item.jellyfin_id)}
          className="rounded bg-gray-700 border-gray-600"
        />
      </td>
      <td className="px-3 py-2.5 max-w-xs">
        <div className="font-medium text-sm text-white truncate">{item.title}</div>
        <div className="text-xs text-gray-600 truncate">{item.file_path}</div>
      </td>
      <td className="px-3 py-2.5 text-center">
        <TierBadge tier={item.storage_tier} />
      </td>
      <td className="px-3 py-2.5 w-32">
        {editTemp ? (
          <form
            className="flex items-center gap-1"
            onSubmit={e => { e.preventDefault(); tempMut.mutate(tempVal) }}
          >
            <input
              type="number" min={0} max={100} step={0.1}
              value={tempVal}
              onChange={e => setTempVal(e.target.value)}
              className="input w-16 py-0.5 text-xs"
              autoFocus
            />
            <button type="submit" className="text-xs text-frost-400 hover:text-frost-300">✓</button>
            <button type="button" onClick={() => setEditTemp(false)} className="text-xs text-gray-500">✕</button>
          </form>
        ) : (
          <button className="w-full text-left hover:opacity-80" onClick={() => { setTempVal(item.temperature.toFixed(1)); setEditTemp(true) }} title="Click to override">
            <TemperatureBar value={item.temperature} />
          </button>
        )}
      </td>
      <td className="px-3 py-2.5 text-xs text-gray-400 text-right tabular-nums">{fmtSize(item.file_size_bytes)}</td>
      <td className="px-3 py-2.5 text-xs text-gray-500 text-right">{fmtDate(item.date_added)}</td>
      <td className="px-3 py-2.5 text-right w-20">
        <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {item.storage_tier === 'hot' && (
            <button className="btn bg-frost-900/40 hover:bg-frost-800/60 text-frost-300 text-xs py-0.5 px-2"
              onClick={() => freeze.mutate()} disabled={freeze.isPending}>Freeze</button>
          )}
          {item.storage_tier === 'cold' && (
            <button className="btn bg-orange-900/40 hover:bg-orange-800/60 text-orange-300 text-xs py-0.5 px-2"
              onClick={() => reheat.mutate()} disabled={reheat.isPending}>Reheat</button>
          )}
        </div>
      </td>
    </tr>
  )
}

// ── Season accordion ────────────────────────────────────────────────────────
function SeasonRow({ season, seriesId }) {
  const [open, setOpen] = useState(false)
  const { data: episodesPage } = useQuery({
    queryKey: ['items', 'eps', seriesId, season.season_number],
    queryFn: () => getItems({ series_id: seriesId, item_type: 'episode', limit: 500 }),
    enabled: open,
  })
  const eps = (episodesPage?.items ?? []).filter(e => e.season_number === season.season_number)

  return (
    <div className="border-t border-gray-800/30">
      <button
        className="w-full flex items-center gap-2 px-4 py-2 hover:bg-gray-800/30 text-left"
        onClick={() => setOpen(v => !v)}
      >
        <span className="text-gray-500 text-xs w-3">{open ? '▾' : '▸'}</span>
        <span className="text-sm text-gray-300">
          {season.season_number != null ? `Season ${season.season_number}` : 'Specials'}
        </span>
        <span className="text-xs text-gray-500 ml-1">{season.episode_count} eps</span>
        <div className="ml-auto flex items-center gap-4">
          <div className="w-20"><TemperatureBar value={season.avg_temperature} showLabel /></div>
          <span className="text-xs text-gray-500 w-16 text-right">{(season.total_size_bytes / 1e9).toFixed(1)} GB</span>
        </div>
      </button>
      {open && (
        <div className="bg-gray-950/30">
          <table className="w-full text-sm">
            <tbody>
              {eps.map(ep => <ItemRow key={ep.id} item={ep} selected={false} onSelect={() => {}} />)}
              {eps.length === 0 && (
                <tr><td colSpan={7} className="px-8 py-3 text-xs text-gray-600">No episodes loaded</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Series card ─────────────────────────────────────────────────────────────
function SeriesCard({ series }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card p-0 overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-800/20 text-left"
        onClick={() => setOpen(v => !v)}
      >
        <span className="text-gray-500 w-3">{open ? '▾' : '▸'}</span>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-white truncate">{series.series_name ?? series.series_id}</div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs text-gray-500">{series.total_episodes} episodes</span>
            <span className="text-xs text-orange-400">🔥 {series.hot_episodes}</span>
            <span className="text-xs text-frost-400">❄️ {series.cold_episodes}</span>
            {series.last_added && (
              <span className="text-xs text-gray-600">Added {series.last_added}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <div className="w-24"><TemperatureBar value={series.avg_temperature} showLabel /></div>
          <span className="text-xs text-gray-500 w-16 text-right">{(series.total_size_bytes / 1e9).toFixed(1)} GB</span>
        </div>
      </button>
      {open && series.seasons.map(s => (
        <SeasonRow key={s.season_number ?? 'specials'} season={s} seriesId={series.series_id} />
      ))}
    </div>
  )
}

// ── Main view ────────────────────────────────────────────────────────────────
export default function Library() {
  const qc = useQueryClient()
  const [mode, setMode] = useState('movies')
  const [search, setSearch] = useState('')
  const [tier, setTier] = useState('')
  const [sort, setSort] = useState('temperature')
  const [order, setOrder] = useState('desc')
  const [seriesSort, setSeriesSort] = useState('temperature')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState(new Set())
  const [libraryTab, setLibraryTab] = useState('all')
  const LIMIT = 100

  const itemsQuery = useQuery({
    queryKey: ['items', mode, search, tier, sort, order, page],
    queryFn: () => getItems({
      item_type: 'movie',
      search: search || undefined,
      tier: tier || undefined,
      sort, order,
      limit: LIMIT,
      offset: page * LIMIT,
    }),
    enabled: mode === 'movies',
    keepPreviousData: true,
  })

  const seriesQuery = useQuery({
    queryKey: ['series', search, seriesSort],
    queryFn: () => getSeries(search, seriesSort),
    enabled: mode === 'series',
  })

  // Derive library tabs dynamically from data
  const allSeries = seriesQuery.data ?? []
  const libraries = useMemo(() => {
    const libs = [...new Set(allSeries.map(s => s.library))].sort()
    return ['all', ...libs]
  }, [allSeries])

  const filteredSeries = libraryTab === 'all'
    ? allSeries
    : allSeries.filter(s => s.library === libraryTab)

  const toggleSelect = useCallback(id => {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }, [])

  const bulkFrzMut = useMutation({
    mutationFn: () => bulkFreeze([...selected]),
    onSuccess: () => { setSelected(new Set()); qc.invalidateQueries({ queryKey: ['items'] }) },
  })
  const bulkRhtMut = useMutation({
    mutationFn: () => bulkReheat([...selected]),
    onSuccess: () => { setSelected(new Set()); qc.invalidateQueries({ queryKey: ['items'] }) },
  })

  const items = itemsQuery.data?.items ?? []
  const total = itemsQuery.data?.total ?? 0
  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Library</h1>
        <div className="flex gap-1">
          {['movies', 'series'].map(m => (
            <button
              key={m}
              className={`btn text-sm capitalize ${mode === m ? 'bg-frost-700 text-white' : 'btn-ghost'}`}
              onClick={() => { setMode(m); setPage(0) }}
            >
              {m === 'movies' ? '🎬 Movies' : '📺 Series'}
            </button>
          ))}
        </div>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="input flex-1 min-w-40 max-w-xs"
          placeholder="Search titles…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0) }}
        />
        {mode === 'movies' && (
          <>
            <select className="select w-36" value={tier} onChange={e => { setTier(e.target.value); setPage(0) }}>
              <option value="">All tiers</option>
              <option value="hot">Hot (NAS)</option>
              <option value="cold">Cold (Cloud)</option>
            </select>
            <select className="select w-36" value={sort} onChange={e => setSort(e.target.value)}>
              <option value="temperature">Temperature</option>
              <option value="title">Title</option>
              <option value="file_size_bytes">Size</option>
              <option value="date_added">Date Added</option>
            </select>
            <button className="btn-ghost text-sm" onClick={() => setOrder(o => o === 'desc' ? 'asc' : 'desc')}>
              {order === 'desc' ? '↓' : '↑'}
            </button>
          </>
        )}
        {mode === 'series' && (
          <select className="select w-36" value={seriesSort} onChange={e => setSeriesSort(e.target.value)}>
            <option value="temperature">Temperature</option>
            <option value="name">Name</option>
            <option value="size">Size</option>
            <option value="date">Date Added</option>
          </select>
        )}
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 bg-frost-900/30 border border-frost-700/40 rounded-xl">
          <span className="text-sm text-frost-300 font-medium">{selected.size} selected</span>
          <button className="btn-ghost text-xs" onClick={() => setSelected(new Set())}>Clear</button>
          <div className="ml-auto flex gap-2">
            <button className="btn bg-frost-900/50 hover:bg-frost-800/60 text-frost-300 text-sm"
              onClick={() => bulkFrzMut.mutate()} disabled={bulkFrzMut.isPending}>
              ❄️ Freeze selected
            </button>
            <button className="btn bg-orange-900/50 hover:bg-orange-800/60 text-orange-300 text-sm"
              onClick={() => bulkRhtMut.mutate()} disabled={bulkRhtMut.isPending}>
              🔥 Reheat selected
            </button>
          </div>
        </div>
      )}

      {/* ── Movies table ─────────────────────────────────────────────────────── */}
      {mode === 'movies' && (
        <div className="card p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                <th className="px-3 py-2.5 w-8">
                  <input type="checkbox"
                    onChange={e => e.target.checked
                      ? setSelected(new Set(items.map(i => i.jellyfin_id)))
                      : setSelected(new Set())}
                    checked={selected.size > 0 && selected.size === items.length}
                    className="rounded bg-gray-700 border-gray-600"
                  />
                </th>
                <th className="px-3 py-2.5 text-left">Title</th>
                <th className="px-3 py-2.5 text-center">Tier</th>
                <th className="px-3 py-2.5 text-left w-32">Temp</th>
                <th className="px-3 py-2.5 text-right">Size</th>
                <th className="px-3 py-2.5 text-right">Added</th>
                <th className="px-3 py-2.5 w-20" />
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <ItemRow key={item.id} item={item} selected={selected.has(item.jellyfin_id)} onSelect={toggleSelect} />
              ))}
              {items.length === 0 && !itemsQuery.isLoading && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-600 text-sm">No items found</td></tr>
              )}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-800 text-xs text-gray-500">
              <span>{total.toLocaleString()} items</span>
              <div className="flex gap-1 items-center">
                <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
                <span className="px-2">{page + 1} / {totalPages}</span>
                <button className="btn-ghost py-1 px-2 text-xs" onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>Next →</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Series tree ───────────────────────────────────────────────────────── */}
      {mode === 'series' && (
        <div className="space-y-3">
          {/* Library tabs — derived dynamically from data */}
          {libraries.length > 2 && (
            <div className="flex gap-1 flex-wrap">
              {libraries.map(lib => (
                <button
                  key={lib}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    libraryTab === lib
                      ? 'bg-frost-600/30 text-frost-300 border border-frost-600/40'
                      : 'bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-gray-700/40'
                  }`}
                  onClick={() => setLibraryTab(lib)}
                >
                  {lib === 'all' ? `All (${allSeries.length})` : `${lib} (${allSeries.filter(s => s.library === lib).length})`}
                </button>
              ))}
            </div>
          )}

          {seriesQuery.isLoading && <div className="text-gray-500 text-sm py-4">Loading series…</div>}

          {filteredSeries.map(s => <SeriesCard key={s.series_id} series={s} />)}

          {!seriesQuery.isLoading && filteredSeries.length === 0 && (
            <div className="text-gray-600 text-sm text-center py-8">No series found</div>
          )}
        </div>
      )}
    </div>
  )
}
