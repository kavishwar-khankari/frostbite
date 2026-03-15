import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getScoreHistory, getItems } from '../api/client'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
  BarChart, Bar, Cell,
} from 'recharts'

function fmtDate(iso) {
  const d = new Date(iso)
  const mo = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${mo}/${day} ${h}:${m}`
}

const BINS = [
  { label: '0–10',  min: 0,  max: 10  },
  { label: '10–20', min: 10, max: 20  },
  { label: '20–30', min: 20, max: 30  },
  { label: '30–40', min: 30, max: 40  },
  { label: '40–50', min: 40, max: 50  },
  { label: '50–60', min: 50, max: 60  },
  { label: '60–70', min: 60, max: 70  },
  { label: '70–80', min: 70, max: 80  },
  { label: '80–90', min: 80, max: 90  },
  { label: '90–100',min: 90, max: 101 },
]

const CHART_STYLE = {
  contentStyle: { backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#9ca3af' },
}

export default function Analytics() {
  const [days, setDays] = useState(30)

  const { data: history = [] } = useQuery({
    queryKey: ['scoreHistory', days],
    queryFn: () => getScoreHistory(days),
    refetchInterval: 60_000,
  })

  const { data: itemsPage } = useQuery({
    queryKey: ['items', 'analytics'],
    queryFn: () => getItems({ limit: 500, sort: 'temperature', order: 'asc' }),
    staleTime: 30_000,
  })
  const items = itemsPage?.items ?? []

  // Temperature histogram
  const histData = BINS.map(bin => ({
    label: bin.label,
    count: items.filter(i => i.temperature >= bin.min && i.temperature < bin.max).length,
  }))

  // Chart data
  const chartData = history.map(h => ({
    date: fmtDate(h.recorded_at),
    hot: h.hot_items,
    cold: h.cold_items,
    avg_temp: parseFloat(h.avg_temperature.toFixed(1)),
    nas_gb: parseFloat((h.nas_used_bytes / 1e9).toFixed(2)),
    cloud_gb: parseFloat((h.cloud_used_bytes / 1e9).toFixed(2)),
  }))

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Analytics</h1>
        <select
          className="select w-28"
          value={days}
          onChange={e => setDays(Number(e.target.value))}
        >
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
          <option value={60}>60 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      {/* Tier count over time */}
      <div className="card">
        <div className="text-sm font-medium text-gray-300 mb-4">Hot vs Cold Items</div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="hotGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="coldGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
            <Tooltip {...CHART_STYLE} />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
            <Area type="monotone" dataKey="hot" stroke="#f97316" fill="url(#hotGrad)" strokeWidth={1.5} name="Hot" dot={false} />
            <Area type="monotone" dataKey="cold" stroke="#38bdf8" fill="url(#coldGrad)" strokeWidth={1.5} name="Cold" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Average temperature trend */}
      <div className="card">
        <div className="text-sm font-medium text-gray-300 mb-4">Average Temperature Trend</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#6b7280' }} />
            <Tooltip {...CHART_STYLE} />
            <Line type="monotone" dataKey="avg_temp" stroke="#a78bfa" dot={false} strokeWidth={2} name="Avg Temp" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Storage usage */}
      <div className="card">
        <div className="text-sm font-medium text-gray-300 mb-4">Storage Usage (GB)</div>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="nasGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="cloudGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
            <Tooltip {...CHART_STYLE} />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
            <Area type="monotone" dataKey="nas_gb" stroke="#f97316" fill="url(#nasGrad)" strokeWidth={1.5} name="NAS (GB)" dot={false} />
            <Area type="monotone" dataKey="cloud_gb" stroke="#38bdf8" fill="url(#cloudGrad)" strokeWidth={1.5} name="Cloud (GB)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Temperature histogram */}
      <div className="card">
        <div className="text-sm font-medium text-gray-300 mb-4">Temperature Distribution</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={histData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
            <Tooltip {...CHART_STYLE} />
            <Bar dataKey="count" name="Items" radius={[3, 3, 0, 0]}>
              {histData.map((entry, i) => {
                const hue = Math.floor((i / histData.length) * 180) // blue→orange
                return <Cell key={i} fill={`hsl(${200 - hue}, 70%, 55%)`} />
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
