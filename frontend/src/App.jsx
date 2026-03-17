import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import PaperList from './pages/PaperList'
import PaperDetail from './pages/PaperDetail'

export default function App() {
  const location = useLocation()
  const isHomePage = location.pathname === '/'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* 顶部导航栏 */}
      <nav className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          {/* 左侧：Logo + 标题 */}
          <Link to="/" className="flex items-center gap-3 group">
            {/* Logo */}
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center group-hover:bg-blue-700 transition-colors">
              <BookOpen className="text-white" size={22} />
            </div>
            {/* 标题 */}
            <div>
              <h1 className="text-lg font-bold text-gray-900 leading-tight">
                ArXiv 论文智能分析
              </h1>
              <p className="text-xs text-gray-500 leading-tight">
                AI-Powered Paper Analysis Platform
              </p>
            </div>
          </Link>

          {/* 右侧：导航链接 */}
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                isHomePage
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`}
            >
              论文列表
            </Link>
          </div>
        </div>
      </nav>

      {/* 主内容区 */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<PaperList />} />
          <Route path="/paper/:id" element={<PaperDetail />} />
        </Routes>
      </main>

      {/* 底部 Footer */}
      <footer className="bg-white border-t border-gray-200 py-4">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <p className="text-sm text-gray-500">
            ArXiv论文智能分析平台 — 基于AI的论文聚合与深度分析系统
          </p>
        </div>
      </footer>
    </div>
  )
}