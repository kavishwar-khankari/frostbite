export default function ProgressBar({ value, max, className = '' }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className={`h-1.5 bg-gray-700 rounded-full overflow-hidden ${className}`}>
      <div
        className="h-full bg-frost-500 rounded-full transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
