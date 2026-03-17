import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import {
  ChevronRight,
  ExternalLink,
  FileText,
  Sparkles,
  RefreshCw,
  CheckCircle,
  Clock,
  Users,
  Building2,
  Calendar,
  Hash,
  Tag,
  BookOpen,
  Target,
  ThumbsUp,
  AlertCircle,
  Rocket,
} from 'lucide-react'
import AnalysisReport from '../components/AnalysisReport'
import { fetchPaperDetail, analyzePaper } from '../api/papers'

// 学科分类颜色映射
const CATEGORY_COLORS = {
  'cs.AI': { bg: 'bg-purple-100', text: 'text-purple-700', border: 'border-purple-200' },
  'cs.CL': { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' },
  'cs.LG': { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200' },
  'cs.CV': { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-200' },
  'cs.NE': { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200' },
  'cs.RO': { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-200' },
  'cs.DB': { bg: 'bg-indigo-100', text: 'text-indigo-700', border: 'border-indigo-200' },
  'cs.DC': { bg: 'bg-teal-100', text: 'text-teal-700', border: 'border-teal-200' },
  'cs.SE': { bg: 'bg-cyan-100', text: 'text-cyan-700', border: 'border-cyan-200' },
  'cs.CR': { bg: 'bg-pink-100', text: 'text-pink-700', border: 'border-pink-200' },
  'stat.ML': { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200' },
}

const DEFAULT_COLOR = { bg: 'bg-gray-100', text: 'text-gray-700', border: 'border-gray-200' }

// 评级颜色映射
const GRADE_COLORS = {
  A: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-300' },
  B: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-300' },
  C: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-300' },
}

export default function PaperDetail() {
  const { id } = useParams()

  // 数据状态
  const [paper, setPaper] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // 分析状态
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisMessage, setAnalysisMessage] = useState(null)
  const [analysisProgress, setAnalysisProgress] = useState('')

  // 标签页状态
  const [activeTab, setActiveTab] = useState('analysis')

  // 分析进度定时器
  const progressTimerRef = useRef(null)
  const progressPhaseRef = useRef(0)

  // 加载论文详情
  const loadPaper = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchPaperDetail(id)
      setPaper(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadPaper()
  }, [loadPaper])

  // 触发分析
  const handleAnalyze = async (forceRefresh = false) => {
    setAnalyzing(true)
    setAnalysisMessage(null)
    setAnalysisProgress('正在初始化...')

    // 进度提示阶段
    const progressPhases = [
      { time: 5000, text: '正在下载 PDF...' },
      { time: 15000, text: '正在提取文本...' },
      { time: 25000, text: 'AI 正在分析论文内容...' },
      { time: 40000, text: '正在生成深度分析报告...' },
      { time: 60000, text: '分析即将完成，请稍候...' },
    ]

    // 设置进度定时器
    progressPhaseRef.current = 0
    const scheduleNextPhase = () => {
      if (progressPhaseRef.current < progressPhases.length) {
        const phase = progressPhases[progressPhaseRef.current]
        progressTimerRef.current = setTimeout(() => {
          setAnalysisProgress(phase.text)
          progressPhaseRef.current++
          scheduleNextPhase()
        }, phase.time - (progressPhaseRef.current > 0 ? progressPhases[progressPhaseRef.current - 1].time : 0))
      }
    }
    scheduleNextPhase()

    try {
      const result = await analyzePaper(id, forceRefresh)
      setAnalysisMessage({ type: 'success', text: '分析完成' })
      // 更新 paper 数据
      setPaper((prev) => ({
        ...prev,
        deep_analysis: result.analysis,
        analysis_json: result.analysis_json,
        has_deep_analysis: true,
      }))
    } catch (err) {
      setAnalysisMessage({ type: 'error', text: `分析失败: ${err.message}` })
    } finally {
      // 清除定时器
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current)
        progressTimerRef.current = null
      }
      setAnalyzing(false)
      setAnalysisProgress('')
    }
  }

  // 组件卸载时清理定时器
  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current)
      }
    }
  }, [])

  // 格式化日期
  const formatDate = (dateStr) => {
    if (!dateStr) return '未知'
    return format(new Date(dateStr), 'yyyy年MM月dd日', { locale: zhCN })
  }

  // 加载中
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex justify-center items-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-500">加载中...</p>
        </div>
      </div>
    )
  }

  // 错误
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex justify-center items-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">加载失败: {error}</p>
          <Link to="/" className="text-blue-600 hover:underline">
            返回首页
          </Link>
        </div>
      </div>
    )
  }

  // 无数据
  if (!paper) {
    return (
      <div className="min-h-screen bg-gray-50 flex justify-center items-center">
        <p className="text-gray-500">论文不存在</p>
      </div>
    )
  }

  const {
    title,
    authors = [],
    categories = [],
    tags = [],
    published_date,
    arxiv_id,
    arxiv_url,
    pdf_url,
    summary,
    institution,
    deep_analysis,
    analysis_json,
    has_deep_analysis,
  } = paper

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 面包屑导航 */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center gap-2 text-sm">
            <Link to="/" className="text-gray-500 hover:text-blue-600 transition-colors">
              论文列表
            </Link>
            <ChevronRight size={16} className="text-gray-400" />
            <span className="text-gray-700 truncate max-w-md">{title}</span>
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* 论文信息卡片 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          {/* 头部：分类 + 已分析标记 */}
          <div className="px-6 pt-5 pb-3 flex items-center justify-between border-b border-gray-100">
            <div className="flex flex-wrap gap-2">
              {categories.map((cat) => {
                const colors = CATEGORY_COLORS[cat] || DEFAULT_COLOR
                return (
                  <span
                    key={cat}
                    className={`px-2.5 py-1 text-xs font-medium rounded ${colors.bg} ${colors.text} ${colors.border} border`}
                  >
                    {cat}
                  </span>
                )
              })}
            </div>
            {has_deep_analysis && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-full">
                <CheckCircle size={14} />
                已分析
              </span>
            )}
          </div>

          {/* 标题 */}
          <div className="px-6 pt-4">
            <h1 className="text-2xl font-bold text-gray-900 leading-tight">{title}</h1>
          </div>

          {/* 元信息网格 */}
          <div className="px-6 py-4 grid grid-cols-2 gap-4">
            {/* 作者 */}
            <div className="flex items-start gap-3">
              <Users size={18} className="text-gray-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs text-gray-400 mb-1">作者</p>
                <p className="text-sm text-gray-700 leading-relaxed">
                  {authors.slice(0, 8).join('、')}
                  {authors.length > 8 && <span className="text-gray-400"> 等{authors.length - 8}人</span>}
                </p>
              </div>
            </div>

            {/* 机构 */}
            {institution && (
              <div className="flex items-start gap-3">
                <Building2 size={18} className="text-gray-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs text-gray-400 mb-1">机构</p>
                  <p className="text-sm text-gray-700">{institution}</p>
                </div>
              </div>
            )}

            {/* 发布日期 */}
            <div className="flex items-start gap-3">
              <Calendar size={18} className="text-gray-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs text-gray-400 mb-1">发布日期</p>
                <p className="text-sm text-gray-700">{formatDate(published_date)}</p>
              </div>
            </div>

            {/* ArXiv ID */}
            <div className="flex items-start gap-3">
              <Hash size={18} className="text-gray-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs text-gray-400 mb-1">ArXiv ID</p>
                <p className="text-sm text-gray-700 font-mono">{arxiv_id}</p>
              </div>
            </div>
          </div>

          {/* 主题标签 */}
          {tags.length > 0 && (
            <div className="px-6 pb-4">
              <div className="flex items-center gap-2 flex-wrap">
                <Tag size={16} className="text-gray-400" />
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2.5 py-1 bg-gray-100 text-gray-600 text-xs rounded-full"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 一句话总结 */}
          {summary && (
            <div className="px-6 pb-4">
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 rounded-xl p-4">
                <p className="text-blue-800 leading-relaxed">{summary}</p>
              </div>
            </div>
          )}

          {/* 操作按钮 */}
          <div className="px-6 pb-4">
            <div className="flex flex-wrap items-center gap-3">
              {/* 主按钮：生成/查看分析 */}
              {has_deep_analysis ? (
                <button
                  onClick={() => setActiveTab('analysis')}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                >
                  <BookOpen size={18} />
                  查看深度分析
                </button>
              ) : (
                <button
                  onClick={() => handleAnalyze(false)}
                  disabled={analyzing}
                  className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {analyzing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      分析中...
                    </>
                  ) : (
                    <>
                      <Sparkles size={18} />
                      生成深度分析
                    </>
                  )}
                </button>
              )}

              {/* 重新分析 */}
              {has_deep_analysis && (
                <button
                  onClick={() => handleAnalyze(true)}
                  disabled={analyzing}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <RefreshCw size={16} />
                  重新分析
                </button>
              )}

              {/* ArXiv 链接 */}
              {arxiv_url && (
                <a
                  href={arxiv_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <ExternalLink size={16} />
                  ArXiv 页面
                </a>
              )}

              {/* PDF 链接 */}
              {pdf_url && (
                <a
                  href={pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  <FileText size={16} />
                  下载 PDF
                </a>
              )}
            </div>

            {/* 分析状态消息 */}
            {analysisMessage && (
              <div
                className={`mt-3 px-4 py-2 rounded-lg text-sm ${
                  analysisMessage.type === 'success'
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700'
                }`}
              >
                {analysisMessage.text}
              </div>
            )}
          </div>
        </div>

        {/* 内容标签页 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          {/* 标签栏 */}
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setActiveTab('analysis')}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${
                activeTab === 'analysis'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              深度分析
            </button>
            <button
              onClick={() => setActiveTab('abstract')}
              className={`flex-1 px-6 py-3 text-sm font-medium transition-colors ${
                activeTab === 'abstract'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              原文摘要
            </button>
          </div>

          {/* 标签页内容 */}
          <div className="p-6">
            {activeTab === 'analysis' ? (
              // 深度分析
              <>
                {analyzing ? (
                  <div className="py-12 text-center">
                    <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mx-auto mb-6" />
                    <p className="text-lg text-gray-700 mb-2">{analysisProgress || 'AI 正在分析...'}</p>
                    <p className="text-sm text-gray-500 max-w-md mx-auto">
                      正在阅读论文内容、提取关键信息、生成深度分析报告，预计需要 30-60 秒
                    </p>
                  </div>
                ) : has_deep_analysis && deep_analysis ? (
                  <AnalysisReport report={deep_analysis} />
                ) : (
                  <div className="py-12 text-center">
                    <Sparkles size={48} className="mx-auto text-gray-300 mb-4" />
                    <p className="text-gray-500 mb-4">尚未生成深度分析</p>
                    <button
                      onClick={() => handleAnalyze(false)}
                      className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      <Sparkles size={18} />
                      生成深度分析
                    </button>
                  </div>
                )}
              </>
            ) : (
              // 原文摘要
              <div className="bg-gray-50 rounded-xl p-6">
                <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                  {paper.abstract || paper.summary || '暂无摘要'}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* 结构化评估卡片 */}
        {has_deep_analysis && analysis_json && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">结构化评估</h2>
            </div>
            <div className="p-6">
              {/* 评级 */}
              {analysis_json.overall_grade && (
                <div className="mb-6 flex items-center gap-3">
                  <span className="text-gray-500">总体评级：</span>
                  <span
                    className={`px-3 py-1 text-lg font-bold rounded-lg border ${
                      GRADE_COLORS[analysis_json.overall_grade]?.bg || 'bg-gray-100'
                    } ${GRADE_COLORS[analysis_json.overall_grade]?.text || 'text-gray-700'} ${
                      GRADE_COLORS[analysis_json.overall_grade]?.border || 'border-gray-300'
                    }`}
                  >
                    {analysis_json.overall_grade}
                  </span>
                </div>
              )}

              {/* 2列网格 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 主要贡献 */}
                {analysis_json.main_contributions && (
                  <EvalCard
                    icon={<Target className="text-blue-500" size={20} />}
                    title="主要贡献"
                    items={Array.isArray(analysis_json.main_contributions) ? analysis_json.main_contributions : [analysis_json.main_contributions]}
                    bgColor="bg-blue-50"
                  />
                )}

                {/* 优势 */}
                {analysis_json.strengths && (
                  <EvalCard
                    icon={<ThumbsUp className="text-green-500" size={20} />}
                    title="优势"
                    items={Array.isArray(analysis_json.strengths) ? analysis_json.strengths : [analysis_json.strengths]}
                    bgColor="bg-green-50"
                  />
                )}

                {/* 不足 */}
                {analysis_json.limitations && (
                  <EvalCard
                    icon={<AlertCircle className="text-orange-500" size={20} />}
                    title="不足"
                    items={Array.isArray(analysis_json.limitations) ? analysis_json.limitations : [analysis_json.limitations]}
                    bgColor="bg-orange-50"
                  />
                )}

                {/* 未来方向 */}
                {analysis_json.future_directions && (
                  <EvalCard
                    icon={<Rocket className="text-purple-500" size={20} />}
                    title="未来方向"
                    items={Array.isArray(analysis_json.future_directions) ? analysis_json.future_directions : [analysis_json.future_directions]}
                    bgColor="bg-purple-50"
                  />
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

// 评估卡片组件
function EvalCard({ icon, title, items, bgColor }) {
  return (
    <div className={`${bgColor} rounded-xl p-4`}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h3 className="font-semibold text-gray-800">{title}</h3>
      </div>
      <ul className="space-y-2">
        {items.map((item, idx) => (
          <li key={idx} className="text-sm text-gray-700 leading-relaxed flex items-start gap-2">
            <span className="text-gray-400 mt-1">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}