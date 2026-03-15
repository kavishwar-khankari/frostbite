export default function TemperatureBar({ value, showLabel = true }) {
  const pct = Math.min(100, Math.max(0, value))
  // cold (blue) → warm (orange) → hot (red)
  const color =
    pct >= 70 ? '#f97316' :
    pct >= 40 ? '#eab308' :
               '#38bdf8'
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      {showLabel && (
        <span className="text-xs tabular-nums text-gray-400 w-8 text-right shrink-0">
          {pct.toFixed(0)}
        </span>
      )}
    </div>
  )
}
