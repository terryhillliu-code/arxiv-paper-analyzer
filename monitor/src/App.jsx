import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Tasks from './pages/Tasks.jsx'
import Quality from './pages/Quality.jsx'
import Performance from './pages/Performance.jsx'
import History from './pages/History.jsx'

const navItems = [
  { path: '/', label: '总览', icon: '📊' },
  { path: '/tasks', label: '任务', icon: '📋' },
  { path: '/quality', label: '质量', icon: '✨' },
  { path: '/performance', label: '性能', icon: '⚡' },
  { path: '/history', label: '历史', icon: '📈' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-arxiv-dark">
        {/* Header */}
        <header className="bg-arxiv-card border-b border-gray-700 px-4 py-3">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <h1 className="text-xl font-bold text-arxiv-primary">
              ArXiv 论文分析监控
            </h1>
            <div className="text-sm text-gray-500">
              每10秒自动刷新
            </div>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-arxiv-card-dark border-b border-gray-700 px-4">
          <div className="max-w-7xl mx-auto flex gap-4">
            {navItems.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `px-4 py-2 text-sm flex items-center gap-1 ${
                    isActive
                      ? 'text-arxiv-primary border-b-2 border-arxiv-primary'
                      : 'text-gray-400 hover:text-gray-200'
                  }`
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        {/* Content */}
        <main className="max-w-7xl mx-auto p-4">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/quality" element={<Quality />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/history" element={<History />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </BrowserRouter>
  )
}