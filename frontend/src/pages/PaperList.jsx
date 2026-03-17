import { useState, useEffect, useCallback } from 'react'
import { FileText, Sparkles, RefreshCw, Download, Brain, TrendingUp, FolderOpen } from 'lucide-react'
import SearchBar from '../components/SearchBar'
import FilterBar from '../components/FilterBar'
import PaperCard from '../components/PaperCard'
import {
  fetchPapers,
  fetchStats,
  triggerFetch,
  generateSummaries,
} from '../api/papers'

// 默认分页大小
const PAGE_SIZE = 20

export default function PaperList() {
  // 数据状态
  const [papers, setPapers] = useState([])
  const [stats, setStats] = useState(null)
  const [totalResults, setTotalResults] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  // UI 状态
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [summarizing, setSummarizing] = useState(false)
  const [actionMessage, setActionMessage] = useState(null)

  // 筛选条件
  const [filters, setFilters] = useState({
    search: '',
    categories: null,
    tags: null,
    date_from: null,
    date_to: null,
    has_analysis: null,
    sort_by: null,
    page: 1,
    page_size: PAGE_SIZE,
  })

  // 加载论文列表
  const loadPapers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchPapers(filters)
      setPapers(data.papers || [])
      setTotalResults(data.total || 0)
      setTotalPages(data.total_pages || 0)
    } catch (err) {
      setError(err.message)
      setPapers([])
    } finally {
      setLoading(false)
    }
  }, [filters])

  // 加载统计数据
  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats()
      setStats(data)
    } catch (err) {
      console.error('加载统计失败:', err)
    }
  }, [])

  // 监听 filters 变化重新加载
  useEffect(() => {
    loadPapers()
  }, [loadPapers])

  // 初始加载统计
  useEffect(() => {
    loadStats()
  }, [loadStats])

  // 搜索处理
  const handleSearch = (searchValue) => {
    setFilters((prev) => ({ ...prev, search: searchValue, page: 1 }))
  }

  // 筛选变化处理
  const handleFilterChange = (newFilters) => {
    setFilters((prev) => ({
      ...prev,
      ...newFilters,
      page: 1, // 筛选变化时重置页码
    }))
  }

  // 分页处理
  const handlePageChange = (newPage) => {
    setFilters((prev) => ({ ...prev, page: newPage }))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // 抓取新论文
  const handleFetch = async () => {
    setFetching(true)
    setActionMessage(null)
    try {
      const result = await triggerFetch('AI', 20)
      setActionMessage({
        type: 'success',
        text: `成功抓取 ${result.total_fetched || 0} 篇论文`,
      })
      loadPapers()
      loadStats()
    } catch (err) {
      setActionMessage({ type: 'error', text: `抓取失败: ${err.message}` })
    } finally {
      setFetching(false)
    }
  }

  // 生成摘要
  const handleSummarize = async () => {
    setSummarizing(true)
    setActionMessage(null)
    try {
      const result = await generateSummaries(10)
      setActionMessage({
        type: 'success',
        text: `已为 ${result.success || 0} 篇论文生成摘要`,
      })
      loadPapers()
    } catch (err) {
      setActionMessage({ type: 'error', text: `生成失败: ${err.message}` })
    } finally {
      setSummarizing(false)
    }
  }

  // 刷新
  const handleRefresh = () => {
    loadPapers()
    loadStats()
    setActionMessage(null)
  }

  // 自动隐藏消息
  useEffect(() => {
    if (actionMessage) {
      const timer = setTimeout(() => setActionMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [actionMessage])

  // 生成页码列表（最多显示7页）
  const getPageNumbers = () => {
    const pages = []
    const maxVisible = 7
    let start = Math.max(1, filters.page - Math.floor(maxVisible / 2))
    let end = Math.min(totalPages, start + maxVisible - 1)

    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1)
    }

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }
    return pages
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 头部 */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-gray-900">ArXiv 论文智能分析平台</h1>
          <p className="text-gray-500 mt-1">AI 驱动的论文检索、分析与知识管理</p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* 统计卡片区 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<FileText className="text-blue-500" size={24} />}
            label="论文总数"
            value={stats?.total_papers || 0}
            bgColor="bg-blue-50"
            iconBg="bg-blue-100"
          />
          <StatCard
            icon={<Brain className="text-green-500" size={24} />}
            label="已分析"
            value={stats?.analyzed_papers || 0}
            bgColor="bg-green-50"
            iconBg="bg-green-100"
          />
          <StatCard
            icon={<TrendingUp className="text-purple-500" size={24} />}
            label="近7天新增"
            value={stats?.recent_papers_count || 0}
            bgColor="bg-purple-50"
            iconBg="bg-purple-100"
          />
          <StatCard
            icon={<FolderOpen className="text-orange-500" size={24} />}
            label="学科分类"
            value={Object.keys(stats?.categories || {}).length}
            bgColor="bg-orange-50"
            iconBg="bg-orange-100"
          />
        </div>

        {/* 操作按钮区 */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleFetch}
            disabled={fetching}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Download size={18} />
            {fetching ? '抓取中...' : '抓取新论文'}
          </button>

          <button
            onClick={handleSummarize}
            disabled={summarizing}
            className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Sparkles size={18} />
            {summarizing ? '生成中...' : 'AI生成摘要'}
          </button>

          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <RefreshCw size={18} />
            刷新
          </button>

          {/* 操作消息 */}
          {actionMessage && (
            <span
              className={`ml-auto px-3 py-1.5 rounded-lg text-sm ${
                actionMessage.type === 'success'
                  ? 'bg-green-100 text-green-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {actionMessage.text}
            </span>
          )}
        </div>

        {/* 搜索栏 */}
        <SearchBar value={filters.search} onChange={handleSearch} />

        {/* 筛选栏 */}
        <FilterBar
          filters={filters}
          onFilterChange={handleFilterChange}
          totalResults={totalResults}
        />

        {/* 错误提示 */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            加载失败: {error}
          </div>
        )}

        {/* 论文列表 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          </div>
        ) : papers.length === 0 ? (
          <div className="text-center py-12">
            <FileText size={48} className="mx-auto text-gray-300 mb-4" />
            <p className="text-gray-500 mb-4">暂无论文数据</p>
            <button
              onClick={handleFetch}
              className="inline-flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Download size={18} />
              抓取新论文
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {papers.map((paper, i) => {
              const index = (filters.page - 1) * PAGE_SIZE + i + 1
              return (
                <PaperCard key={paper.id} paper={paper} index={index} />
              )
            })}
          </div>
        )}

        {/* 分页器 */}
        {totalPages > 1 && (
          <div className="flex justify-center items-center gap-2 py-6">
            {/* 上一页 */}
            <button
              onClick={() => handlePageChange(filters.page - 1)}
              disabled={filters.page <= 1}
              className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              上一页
            </button>

            {/* 页码 */}
            <div className="flex gap-1">
              {getPageNumbers().map((pageNum) => (
                <button
                  key={pageNum}
                  onClick={() => handlePageChange(pageNum)}
                  className={`w-10 h-10 text-sm rounded-lg transition-colors ${
                    pageNum === filters.page
                      ? 'bg-blue-600 text-white'
                      : 'border border-gray-200 bg-white hover:bg-gray-50'
                  }`}
                >
                  {pageNum}
                </button>
              ))}
            </div>

            {/* 下一页 */}
            <button
              onClick={() => handlePageChange(filters.page + 1)}
              disabled={filters.page >= totalPages}
              className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              下一页
            </button>
          </div>
        )}
      </main>
    </div>
  )
}

// 统计卡片组件
function StatCard({ icon, label, value, bgColor, iconBg }) {
  return (
    <div className={`${bgColor} rounded-xl p-4 flex items-center gap-4`}>
      <div className={`${iconBg} p-3 rounded-lg`}>{icon}</div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  )
}