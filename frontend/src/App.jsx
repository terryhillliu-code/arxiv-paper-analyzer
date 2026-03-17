import { Routes, Route, Link, useLocation } from 'react-router-dom'
import PaperList from './pages/PaperList'
import PaperDetail from './pages/PaperDetail'

export default function App() {
  const location = useLocation()
  const isHomePage = location.pathname === '/'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* 顶部导航栏 */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center">
          {/* 左侧：标题 */}
          <Link to="/" className="flex items-center gap-2">
            <span className="text-xl font-bold text-purple-700">
              ArXiv 论文智能分析平台
            </span>
            <span className="text-xs text-gray-400 italic">
              @powered by Claude
            </span>
          </Link>
        </div>
      </nav>

      {/* 二级导航 */}
      <div className="bg-white border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex items-center gap-6 h-10">
            <Link
              to="/"
              className={`text-sm transition-colors ${
                !isHomePage
                  ? 'text-gray-500 hover:text-gray-700'
                  : 'text-gray-400 cursor-default'
              }`}
            >
              个人空间
            </Link>
            <Link
              to="/"
              className={`text-sm transition-colors ${
                isHomePage
                  ? 'text-purple-700 border-b-2 border-purple-700 pb-1'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              📋 论文精选
            </Link>
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<PaperList />} />
          <Route path="/paper/:id" element={<PaperDetail />} />
        </Routes>
      </main>

      {/* 底部 Footer */}
      <footer className="bg-white border-t border-gray-200 py-3">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <p className="text-xs text-gray-400">
            © 2024 ArXiv 论文智能分析平台. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  )
}