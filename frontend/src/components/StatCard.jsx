export default function StatCard({ label, value, sub, accent }) {
  const accentMap = {
    blue:   'border-frost-700/50 bg-frost-900/20',
    orange: 'border-orange-700/50 bg-orange-900/20',
    purple: 'border-purple-700/50 bg-purple-900/20',
    green:  'border-emerald-700/50 bg-emerald-900/20',
    red:    'border-red-700/50 bg-red-900/20',
  }
  return (
    <div className={`card border ${accentMap[accent] || 'border-gray-800'}`}>
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}
