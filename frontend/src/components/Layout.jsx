import { NavLink, Outlet } from 'react-router-dom'
import { useWebSocket } from '../hooks/useWebSocket'

const NAV = [
  { to: '/overview',  label: 'Overview',   icon: '📊' },
  { to: '/library',   label: 'Library',    icon: '🎬' },
  { to: '/transfers', label: 'Transfers',  icon: '🔄' },
  { to: '/analytics', label: 'Analytics',  icon: '📈' },
  { to: '/settings',  label: 'Settings',   icon: '⚙️'  },
]

export default function Layout() {
  useWebSocket()

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-2xl">❄️</span>
            <div>
              <div className="font-bold text-white tracking-tight">Frostbite</div>
              <div className="text-xs text-gray-500">Teapot Storage Engine</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-0.5">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-frost-600/20 text-frost-300 font-medium'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`
              }
            >
              <span>{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-600">
          v1.0.0
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
