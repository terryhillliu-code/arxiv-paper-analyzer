import { useState, useEffect, useCallback } from 'react'
import PaperCard from '../components/PaperCard'
import {
  fetchPapers,
  fetchStats,
  fetchPapersByDateRange,
  generateSummaries,
} from '../api/papers'

// 默认分页大小
const PAGE_SIZE = 20

// 学科分类选项
const CATEGORY_OPTIONS = [
  { value: null, label: 'All' },
  { value: 'cs.AI', label: 'cs.AI' },
  { value: 'cs.CL', label: 'cs.CL' },
  { value: 'cs.LG', label: 'cs.LG' },
  { value: 'cs.CV', label: 'cs.CV' },
  { value: 'cs.DC', label: 'cs.DC' },
  { value: 'cs.NE', label: 'cs.NE' },
  { value: 'cs.IR', label: 'cs.IR' },
]

// 智能分类/主题标签选项
const TAG_OPTIONS = [
  { value: null, label: '全部' },
  { value: 'GPU硬件架构', label: 'GPU硬件架构及性能优化' },
  { value: 'AI集群', label: 'AI集群和数据中心' },
  { value: '大模型基础架构', label: '大模型基础架构' },
  { value: '训练推理框架', label: '训练推理框架' },
  { value: '代码生成', label: '代码生成' },
  { value: '图像视频生成', label: '图像&视频生成' },
  { value: '多模态', label: '多模态' },
  { value: '计算机存储', label: '计算机存储' },
  { value: '故障诊断', label: '故障诊断' },
]

// Tier 等级选项
const TIER_OPTIONS = [
  { value: null, label: '全部' },
  { value: 'A', label: 'Tier A (顶尖)' },
  { value: 'B', label: 'Tier B (有价值)' },
  { value: 'C', label: 'Tier C (一般参考)' },
]

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

  // 筛选条件
  const [search, setSearch] = useState('')
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [selectedTag, setSelectedTag] = useState(null)
  const [selectedTier, setSelectedTier] = useState(null)
  const [dateFrom, setDateFrom] = useState('')
  const [sortBy, setSortBy] = useState(null)  // null: 显示所有, 'newest': 最新发布
  const [page, setPage] = useState(1)

  // 加载论文列表
  const loadPapers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = {
        page,
        page_size: PAGE_SIZE,
      }
      if (search) params.search = search
      if (selectedCategory) params.categories = selectedCategory
      if (selectedTag) params.tags = selectedTag
      if (selectedTier) params.tier = selectedTier
      if (sortBy) params.sort_by = sortBy  // 只在设置了排序时才传递
      if (dateFrom) {
        // 选择日期时，同时设置 date_from 和 date_to，精确匹配当天
        params.date_from = dateFrom
        params.date_to = dateFrom
      }

      const data = await fetchPapers(params)
      setPapers(data.papers || [])
      setTotalResults(data.total || 0)
      setTotalPages(data.total_pages || 0)
    } catch (err) {
      setError(err.message)
      setPapers([])
    } finally {
      setLoading(false)
    }
  }, [search, selectedCategory, selectedTag, selectedTier, dateFrom, sortBy, page])

  // 加载统计数据
  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats()
      setStats(data)
    } catch (err) {
      console.error('加载统计失败:', err)
    }
  }, [])

  // 监听筛选条件变化
  useEffect(() => {
    loadPapers()
  }, [loadPapers])

  // 初始加载统计
  useEffect(() => {
    loadStats()
  }, [loadStats])

  // 搜索处理
  const handleSearch = (e) => {
    setSearch(e.target.value)
    setPage(1)
  }

  // 分类选择
  const handleCategorySelect = (value) => {
    setSelectedCategory(value)
    setPage(1)
  }

  // 标签选择
  const handleTagSelect = (value) => {
    setSelectedTag(value)
    setPage(1)
  }

  // Tier 选择
  const handleTierSelect = (value) => {
    setSelectedTier(value)
    setPage(1)
  }

  // 日期变化
  const handleDateChange = (e) => {
    setDateFrom(e.target.value)
    setPage(1)
  }

  // 排序切换：在"全部"和"最新发布"之间切换
  const toggleSort = () => {
    setSortBy((prev) => (prev === 'newest' ? null : 'newest'))
    setPage(1)
  }

  // 刷新
  const handleRefresh = () => {
    loadPapers()
    loadStats()
  }

  // 抓取论文（全量抓取昨天和今天）
  const handleFetch = async () => {
    setFetching(true)
    try {
      const result = await fetchPapersByDateRange()
      console.log('抓取结果:', result)
      loadPapers()
      loadStats()
    } catch (err) {
      console.error('抓取失败:', err)
    } finally {
      setFetching(false)
    }
  }

  // 生成摘要
  const handleSummarize = async () => {
    setSummarizing(true)
    try {
      await generateSummaries(10)
      loadPapers()
    } catch (err) {
      console.error('生成摘要失败:', err)
    } finally {
      setSummarizing(false)
    }
  }

  // 分页处理
  const handlePageChange = (newPage) => {
    setPage(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // 生成页码列表
  const getPageNumbers = () => {
    const pages = []
    const maxVisible = 7
    let start = Math.max(1, page - Math.floor(maxVisible / 2))
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
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* 区域1：分类选择 + 统计数字 */}
        <div className="flex justify-between gap-6">
          {/* 左侧：分类按钮 */}
          <div className="flex-1 space-y-4">
            {/* 学科分类 */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-bold text-gray-500 uppercase">
                CATEGORY
              </span>
              {CATEGORY_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => handleCategorySelect(opt.value)}
                  className={`rounded-full px-4 py-1.5 text-sm transition-colors ${
                    selectedCategory === opt.value
                      ? 'bg-gray-800 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* 智能分类 */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-bold text-gray-500">
                智能分类
              </span>
              {TAG_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => handleTagSelect(opt.value)}
                  className={`rounded-full px-4 py-1.5 text-sm transition-colors ${
                    selectedTag === opt.value
                      ? 'bg-gray-800 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Tier 筛选 */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-bold text-gray-500">
                TIER
              </span>
              {TIER_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => handleTierSelect(opt.value)}
                  className={`rounded-full px-4 py-1.5 text-sm transition-colors ${
                    selectedTier === opt.value
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* 右侧：统计数字 */}
          <div className="bg-white rounded-xl p-6 min-w-[200px]">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <p className="text-sm text-gray-500 mb-1">平台论文总量</p>
                <p className="text-3xl font-bold text-purple-700">
                  {stats?.total_papers || 0}
                </p>
                <p className="text-xs text-gray-400">篇</p>
              </div>
              <div>
                <p className="text-sm text-gray-500 mb-1">当前筛选结果</p>
                <p className="text-3xl font-bold text-gray-900">
                  {totalResults}
                </p>
                <p className="text-xs text-gray-400">篇</p>
              </div>
            </div>
          </div>
        </div>

        {/* 区域2：搜索和 FILTER 栏 */}
        <div className="space-y-3">
          {/* 搜索框 */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              🔍
            </span>
            <input
              type="text"
              value={search}
              onChange={handleSearch}
              placeholder="搜索论文"
              className="w-full border border-gray-300 rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
          </div>

          {/* FILTER 行 */}
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-bold text-gray-500">FILTER</span>

            {/* 日期选择 */}
            <input
              type="date"
              value={dateFrom}
              onChange={handleDateChange}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />

            {/* 排序按钮：按下显示最新，不按显示全部 */}
            <button
              onClick={toggleSort}
              className={`border rounded-lg px-3 py-1.5 text-sm transition-colors ${
                sortBy === 'newest'
                  ? 'border-purple-700 text-purple-700 bg-purple-50'
                  : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {sortBy === 'newest' ? '最新发布' : '全部'}
            </button>

            {/* 刷新按钮 */}
            <button
              onClick={handleRefresh}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              🔄 刷新
            </button>

            {/* 抓取论文按钮 */}
            <button
              onClick={handleFetch}
              disabled={fetching}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {fetching && (
                <span className="w-4 h-4 border-2 border-gray-300 border-t-purple-700 rounded-full animate-spin" />
              )}
              抓取论文
            </button>

            {/* AI摘要按钮 */}
            <button
              onClick={handleSummarize}
              disabled={summarizing}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {summarizing && (
                <span className="w-4 h-4 border-2 border-gray-300 border-t-purple-700 rounded-full animate-spin" />
              )}
              AI摘要
            </button>
          </div>
        </div>

        {/* 区域3：论文列表 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="w-10 h-10 border-4 border-gray-200 border-t-purple-700 rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            加载失败: {error}
          </div>
        ) : papers.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
            <p className="text-gray-500 mb-4">暂无论文，点击抓取论文按钮获取</p>
            <button
              onClick={handleFetch}
              disabled={fetching}
              className="border border-gray-300 rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              抓取论文
            </button>
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-200 bg-white rounded-xl overflow-hidden">
              {papers.map((paper, i) => (
                <PaperCard
                  key={paper.id}
                  paper={paper}
                  index={(page - 1) * PAGE_SIZE + i + 1}
                />
              ))}
            </div>

            {/* 底部提示 */}
            <div className="text-center py-4 border-t border-gray-200">
              <p className="text-sm text-gray-500">
                已加载全部 {totalResults} 篇论文
              </p>
            </div>

            {/* 分页器 */}
            {totalPages > 1 && (
              <div className="flex justify-center items-center gap-2 py-4">
                <button
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page <= 1}
                  className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  上一页
                </button>

                <div className="flex gap-1">
                  {getPageNumbers().map((pageNum) => (
                    <button
                      key={pageNum}
                      onClick={() => handlePageChange(pageNum)}
                      className={`w-10 h-10 text-sm rounded-lg transition-colors ${
                        pageNum === page
                          ? 'bg-purple-700 text-white'
                          : 'border border-gray-200 bg-white hover:bg-gray-50'
                      }`}
                    >
                      {pageNum}
                    </button>
                  ))}
                </div>

                <button
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= totalPages}
                  className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}