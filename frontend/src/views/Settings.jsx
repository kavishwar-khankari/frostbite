import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSettings, updateSetting } from '../api/client'

const SETTING_META = {
  freeze_threshold: {
    label: 'Freeze Threshold',
    desc: 'Items with temperature below this value are candidates for freezing to cold storage.',
    min: 0, max: 100, step: 1, unit: '°',
  },
  reheat_threshold: {
    label: 'Reheat Threshold',
    desc: 'Items that score above this value will be reheated back to NAS.',
    min: 0, max: 100, step: 1, unit: '°',
  },
  prefetch_boost: {
    label: 'Prefetch Boost',
    desc: 'Temperature boost applied when a partially-watched item is predicted to be resumed.',
    min: 0, max: 100, step: 1, unit: '°',
  },
  freeze_window_start: {
    label: 'Freeze Window Start',
    desc: 'Hour of day (local time) when freeze transfers may begin (0–23).',
    min: 0, max: 23, step: 1, unit: 'h',
  },
  freeze_window_end: {
    label: 'Freeze Window End',
    desc: 'Hour of day (local time) when freeze transfers must stop.',
    min: 0, max: 23, step: 1, unit: 'h',
  },
  max_concurrent_reheats: {
    label: 'Max Concurrent Reheats',
    desc: 'Simultaneous reheat (cloud→NAS) transfers. OpenDrive download is unthrottled (~5–11 MB/s per file).',
    min: 1, max: 8, step: 1, unit: '',
  },
  max_concurrent_freezes: {
    label: 'Max Concurrent Freezes',
    desc: 'Simultaneous freeze (NAS→cloud) transfers. OpenDrive upload is throttled (~300 KB/s–1.5 MB/s per file).',
    min: 1, max: 8, step: 1, unit: '',
  },
  emergency_freeze_threshold_gb: {
    label: 'Emergency Freeze Threshold',
    desc: 'When NAS free space drops below this value, emergency freezes are triggered.',
    min: 0, max: 10000, step: 10, unit: ' GB',
  },
}

function SettingRow({ name, value, onSave }) {
  const meta = SETTING_META[name] ?? { label: name, desc: '', min: 0, max: 9999, step: 1, unit: '' }
  const [draft, setDraft] = useState(String(value))
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setDraft(String(value))
    setDirty(false)
  }, [value])

  const handleChange = e => {
    setDraft(e.target.value)
    setDirty(String(value) !== e.target.value)
    setSaved(false)
  }

  const save = () => {
    const n = parseFloat(draft)
    if (!isNaN(n)) {
      onSave(name, n, () => setSaved(true))
      setDirty(false)
    }
  }

  return (
    <div className="py-4 border-b border-gray-800/60 last:border-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="text-sm font-medium text-white">{meta.label}</div>
          <div className="text-xs text-gray-500 mt-0.5">{meta.desc}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <input
            type="number"
            min={meta.min}
            max={meta.max}
            step={meta.step}
            value={draft}
            onChange={handleChange}
            className="input w-24 text-right"
          />
          <span className="text-xs text-gray-500 w-6">{meta.unit}</span>
          <button
            className={`btn text-xs py-1.5 px-3 ${dirty ? 'btn-primary' : saved ? 'bg-emerald-900/30 text-emerald-400 cursor-default' : 'btn-ghost opacity-40 cursor-default'}`}
            onClick={dirty ? save : undefined}
            disabled={!dirty}
          >
            {saved ? '✓ Saved' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const mut = useMutation({
    mutationFn: ({ key, value }) => updateSetting(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })

  const handleSave = (key, value, onDone) => {
    mut.mutate({ key, value }, { onSuccess: onDone })
  }

  if (isLoading) {
    return <div className="p-6 text-gray-500 text-sm">Loading…</div>
  }

  return (
    <div className="p-6 space-y-4 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Changes take effect immediately — no restart required.
        </p>
      </div>

      <div className="card">
        {Object.entries(settings ?? {}).map(([key, value]) => (
          <SettingRow key={key} name={key} value={value} onSave={handleSave} />
        ))}
      </div>

      {mut.isError && (
        <div className="text-sm text-red-400 px-1">
          Error: {mut.error?.message}
        </div>
      )}
    </div>
  )
}
