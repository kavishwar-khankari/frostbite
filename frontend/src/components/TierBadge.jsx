export default function TierBadge({ tier }) {
  if (tier === 'hot') return <span className="badge-hot">🔥 Hot</span>
  if (tier === 'cold') return <span className="badge-cold">❄️ Cold</span>
  return <span className="badge-transferring">⟳ Moving</span>
}
