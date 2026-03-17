import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import AnalysisReport from '../components/AnalysisReport'
import { fetchPaperDetail, analyzePaper } from '../api/papers'

// 学科分类颜色映射
const CATEGORY_COLORS = {
  'cs.AI': 'bg-purple-100 text-purple-700',
  'cs.CL': 'bg-blue-100 text-blue-700',
  'cs.LG': 'bg-green-100 text-green-700',
  'cs.CV': 'bg-orange-100 text-orange-700',
  'cs.NE': 'bg-red-100 text-red-700',
  'cs.DC': 'bg-teal-100 text-teal-700',
  'cs.IR': 'bg-sky-100 text-sky-700',
  'cs.RO': 'bg-yellow-100 text-yellow-700',
  'cs.SE': 'bg-cyan-100 text-cyan-700',
  'cs.CR': 'bg-pink-100 text-pink-700',
  'stat.ML': 'bg-emerald-100 text-emerald-700',
}
const DEFAULT_COLOR = 'bg-gray-100 text-gray-600'

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

    const progressPhases = [
      { time: 5000, text: '正在下载 PDF...' },
      { time: 15000, text: '正在提取文本...' },
      { time: 25000, text: 'AI 正在分析论文内容...' },
      { time: 40000, text: '正在生成深度分析报告...' },
      { time: 60000, text: '分析即将完成，请稍候...' },
    ]

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
      setPaper((prev) => ({
        ...prev,
        analysis_report: result.report,
        analysis_json: result.analysis_json,
        has_analysis: true,
      }))
    } catch (err) {
      setAnalysisMessage({ type: 'error', text: `分析失败: ${err.message}` })
    } finally {
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

  // 格式化中文日期
  const formatChineseDate = (dateStr) => {
    if (!dateStr) return '未知'
    return format(new Date(dateStr), 'yyyy年M月d日', { locale: zhCN })
  }

  // 格式化简短日期
  const formatShortDate = (dateStr) => {
    if (!dateStr) return '未知'
    return format(new Date(dateStr), 'yyyy-MM-dd')
  }

  // 加载中
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex justify-center items-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-gray-200 border-t-purple-700 rounded-full animate-spin mx-auto mb-4" />
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
          <Link to="/" className="text-purple-700 hover:underline">
            返回列表
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
    publish_date,
    created_at,
    arxiv_url,
    pdf_url,
    summary,
    institutions = [],
    analysis_report,
    analysis_json,
    has_analysis,
  } = paper

  const mainTag = tags && tags.length > 0 ? tags[0] : null

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* 顶部返回链接 */}
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-gray-500 hover:text-purple-700 transition-colors"
        >
          ← 返回
        </Link>

        {/* 卡片1：基础信息 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          {/* 右上角主题标签 */}
          {mainTag && (
            <div className="float-right">
              <span className="text-purple-700">{mainTag}</span>
            </div>
          )}

          {/* 标题 */}
          <h1 className="text-2xl font-bold text-gray-900 mb-4 clear-right">
            {title}
          </h1>

          {/* 信息行 */}
          <div className="space-y-2 text-sm">
            <p>
              <span className="font-bold">作者：</span>
              <span className="text-gray-700">
                {authors.length > 0 ? authors.join('、') : '未知'}
              </span>
            </p>

            {institutions && institutions.length > 0 && (
              <p>
                <span className="font-bold">机构：</span>
                <span className="text-purple-700 font-bold italic">
                  {institutions[0]}
                </span>
                {institutions.length > 1 && (
                  <span className="text-gray-700">
                    、{institutions.slice(1).join('、')}
                  </span>
                )}
              </p>
            )}

            <p>
              <span className="font-bold">发布时间：</span>
              <span className="text-gray-700">{formatChineseDate(publish_date)}</span>
            </p>

            <p>
              <span className="font-bold">入库时间：</span>
              <span className="text-gray-700">{formatShortDate(created_at)}</span>
            </p>

            <p className="flex items-center gap-2 flex-wrap">
              <span className="font-bold">论文类型：</span>
              {categories.map((cat) => (
                <span
                  key={cat}
                  className={`px-2 py-0.5 rounded text-xs ${
                    CATEGORY_COLORS[cat] || DEFAULT_COLOR
                  }`}
                >
                  {cat}
                </span>
              ))}
            </p>
          </div>

          {/* 按钮 */}
          <div className="mt-6 space-y-3">
            {arxiv_url && (
              <a
                href={arxiv_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full border border-gray-300 rounded-lg py-3 text-center text-gray-700 hover:bg-gray-50 transition-colors"
              >
                📄 查看 ArXiv 页面
              </a>
            )}
            {pdf_url && (
              <a
                href={pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full border border-gray-300 rounded-lg py-3 text-center text-gray-700 hover:bg-gray-50 transition-colors"
              >
                📑 下载 PDF
              </a>
            )}
          </div>
        </div>

        {/* 卡片2：一段话总结 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-gray-200">
            一段话总结
          </h2>
          {summary ? (
            <p className="text-gray-700 leading-relaxed">{summary}</p>
          ) : (
            <p className="text-gray-500">暂无总结，请先生成AI摘要</p>
          )}
        </div>

        {/* 卡片3：思维导图/论文大纲 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-gray-200">
            思维导图
          </h2>
          {analysis_json?.outline ? (
            <OutlineTree outline={analysis_json.outline} />
          ) : (
            <p className="text-gray-500">
              点击下方按钮生成深度分析后显示
            </p>
          )}
        </div>

        {/* 卡片4：深度分析 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-gray-200">
            深度分析
          </h2>

          {/* 未分析 */}
          {!has_analysis && !analyzing && (
            <button
              onClick={() => handleAnalyze(false)}
              className="w-full py-3 bg-purple-700 text-white rounded-lg hover:bg-purple-800 transition-colors"
            >
              生成深度分析
            </button>
          )}

          {/* 分析中 */}
          {analyzing && (
            <div className="py-8 text-center">
              <div className="w-12 h-12 border-4 border-gray-200 border-t-purple-700 rounded-full animate-spin mx-auto mb-4" />
              <p className="text-gray-700">{analysisProgress || 'AI正在分析论文...'}</p>
            </div>
          )}

          {/* 已分析 */}
          {has_analysis && !analyzing && analysis_report && (
            <>
              <AnalysisReport report={analysis_report} />
              {analysisMessage && (
                <p
                  className={`mt-4 text-sm ${
                    analysisMessage.type === 'success'
                      ? 'text-green-600'
                      : 'text-red-600'
                  }`}
                >
                  {analysisMessage.text}
                </p>
              )}
              <div className="mt-4 pt-4 border-t border-gray-200">
                <button
                  onClick={() => handleAnalyze(true)}
                  disabled={analyzing}
                  className="border border-gray-300 rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  重新分析
                </button>
              </div>
            </>
          )}
        </div>

        {/* 卡片5：综合评估 */}
        {has_analysis && analysis_json && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-xl font-bold mb-4 pb-2 border-b border-gray-200">
              综合评估
            </h2>
            <div className="grid grid-cols-2 gap-6">
              {/* 主要贡献 */}
              {analysis_json.main_contributions && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">
                    主要贡献
                  </h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.main_contributions)
                      ? analysis_json.main_contributions
                      : [analysis_json.main_contributions]
                    ).map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 优势 */}
              {analysis_json.strengths && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">优势</h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.strengths)
                      ? analysis_json.strengths
                      : [analysis_json.strengths]
                    ).map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 不足 */}
              {analysis_json.limitations && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">不足</h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.limitations)
                      ? analysis_json.limitations
                      : [analysis_json.limitations]
                    ).map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 未来方向 */}
              {analysis_json.future_directions && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">
                    未来方向
                  </h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.future_directions)
                      ? analysis_json.future_directions
                      : [analysis_json.future_directions]
                    ).map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// 大纲树形组件
function OutlineTree({ outline }) {
  if (!outline) return null

  const items = Array.isArray(outline) ? outline : [outline]

  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <OutlineItem key={i} item={item} depth={0} />
      ))}
    </ul>
  )
}

function OutlineItem({ item, depth }) {
  if (typeof item === 'string') {
    return (
      <li
        className="text-sm text-gray-700"
        style={{ paddingLeft: depth * 16 }}
      >
        • {item}
      </li>
    )
  }

  const { title, children } = item

  return (
    <li style={{ paddingLeft: depth * 16 }}>
      <span className="text-sm font-medium text-gray-800">{title}</span>
      {children && children.length > 0 && (
        <ul className="mt-1 space-y-1">
          {children.map((child, i) => (
            <OutlineItem key={i} item={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  )
}