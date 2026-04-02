import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import MindMap from 'simple-mind-map'
import 'simple-mind-map/dist/simpleMindMap.esm.css'
import AnalysisReport from '../components/AnalysisReport'
import { PaperDetailSkeleton } from '../components/Skeleton'
import { fetchPaperDetail, createAnalysisTask, getTaskStatus } from '../api/papers'

// 学科分类颜色映射 - 扩展版
const CATEGORY_COLORS = {
  // 计算机科学
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
  'cs.HC': 'bg-indigo-100 text-indigo-700',
  'cs.MM': 'bg-rose-100 text-rose-700',
  'cs.DB': 'bg-amber-100 text-amber-700',
  'cs.GR': 'bg-lime-100 text-lime-700',
  'cs.NI': 'bg-emerald-100 text-emerald-700',
  'cs.OS': 'bg-violet-100 text-violet-700',
  'cs.PL': 'bg-fuchsia-100 text-fuchsia-700',
  'cs.SC': 'bg-slate-100 text-slate-700',
  'cs.SI': 'bg-zinc-100 text-zinc-700',
  'cs.SY': 'bg-stone-100 text-stone-700',
  'cs.MA': 'bg-red-100 text-red-700',
  'cs.CC': 'bg-orange-100 text-orange-700',
  'cs.CG': 'bg-teal-100 text-teal-700',
  'cs.DS': 'bg-blue-100 text-blue-700',
  'cs.ET': 'bg-purple-100 text-purple-700',
  'cs.FL': 'bg-pink-100 text-pink-700',
  'cs.GL': 'bg-green-100 text-green-700',
  'cs.GT': 'bg-yellow-100 text-yellow-700',
  'cs.AR': 'bg-indigo-100 text-indigo-700',
  'cs.CY': 'bg-cyan-100 text-cyan-700',
  'cs.MS': 'bg-sky-100 text-sky-700',
  'cs.NA': 'bg-amber-100 text-amber-700',
  'cs.PF': 'bg-lime-100 text-lime-700',
  'cs.QL': 'bg-violet-100 text-violet-700',
  'cs.SD': 'bg-fuchsia-100 text-fuchsia-700',
  // 统计学
  'stat.ML': 'bg-emerald-100 text-emerald-700',
  'stat.CO': 'bg-teal-100 text-teal-700',
  'stat.TH': 'bg-green-100 text-green-700',
  'stat.ME': 'bg-lime-100 text-lime-700',
  // 数学
  'math.OC': 'bg-blue-100 text-blue-700',
  'math.NA': 'bg-indigo-100 text-indigo-700',
  'math.ST': 'bg-purple-100 text-purple-700',
  'math.PR': 'bg-pink-100 text-pink-700',
  'math.LO': 'bg-violet-100 text-violet-700',
  // 物理
  'physics.comp-ph': 'bg-cyan-100 text-cyan-700',
  'physics.data-an': 'bg-sky-100 text-sky-700',
  // 电子工程
  'eess.AS': 'bg-amber-100 text-amber-700',
  'eess.IV': 'bg-orange-100 text-orange-700',
  'eess.SP': 'bg-yellow-100 text-yellow-700',
  'eess.SY': 'bg-lime-100 text-lime-700',
  // 量化金融
  'q-bio.QM': 'bg-rose-100 text-rose-700',
  'q-bio.BM': 'bg-red-100 text-red-700',
  'q-bio.CB': 'bg-orange-100 text-orange-700',
  'q-bio.GN': 'bg-amber-100 text-amber-700',
  'q-bio.MN': 'bg-yellow-100 text-yellow-700',
  'q-bio.NC': 'bg-lime-100 text-lime-700',
  'q-bio.PE': 'bg-green-100 text-green-700',
  'q-bio.SC': 'bg-emerald-100 text-emerald-700',
  'q-bio.TO': 'bg-teal-100 text-teal-700',
  // 量化金融
  'q-fin.CP': 'bg-cyan-100 text-cyan-700',
  'q-fin.EC': 'bg-sky-100 text-sky-700',
  'q-fin.GN': 'bg-blue-100 text-blue-700',
  'q-fin.MF': 'bg-indigo-100 text-indigo-700',
  'q-fin.PM': 'bg-violet-100 text-violet-700',
  'q-fin.PR': 'bg-purple-100 text-purple-700',
  'q-fin.RM': 'bg-fuchsia-100 text-fuchsia-700',
  'q-fin.ST': 'bg-pink-100 text-pink-700',
  'q-fin.TR': 'bg-rose-100 text-rose-700',
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
  const abortControllerRef = useRef(null) // 用于取消请求

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

  // 触发分析（异步任务模式）
  const handleAnalyze = async (forceRefresh = false) => {
    setAnalyzing(true)
    setAnalysisMessage(null)
    setAnalysisProgress('正在创建分析任务...')

    // 创建新的 AbortController
    abortControllerRef.current = new AbortController()

    try {
      // 创建异步任务
      const task = await createAnalysisTask(id, true, forceRefresh)
      const taskId = task.id

      setAnalysisProgress(task.message || '任务已创建，正在处理...')

      // 轮询配置
      const pollInterval = 2000 // 2秒轮询一次
      const maxPolls = 300 // 最多轮询 300 次 (10分钟)
      const timeoutMs = 10 * 60 * 1000 // 10分钟总超时
      const startTime = Date.now()
      let pollCount = 0
      let completed = false

      while (!completed) {
        // 检查是否被取消
        if (abortControllerRef.current?.signal.aborted) {
          setAnalysisMessage({ type: 'error', text: '分析已取消' })
          break
        }

        // 检查超时
        if (Date.now() - startTime > timeoutMs) {
          setAnalysisMessage({ type: 'error', text: '分析超时（超过10分钟），请稍后刷新页面查看结果' })
          break
        }

        // 检查最大轮询次数
        pollCount++
        if (pollCount > maxPolls) {
          setAnalysisMessage({ type: 'error', text: '分析时间过长，请稍后刷新页面查看结果' })
          break
        }

        await new Promise(resolve => setTimeout(resolve, pollInterval))

        // 再次检查是否被取消
        if (abortControllerRef.current?.signal.aborted) {
          setAnalysisMessage({ type: 'error', text: '分析已取消' })
          break
        }

        const status = await getTaskStatus(taskId)

        // 更新进度显示
        if (status.progress > 0) {
          setAnalysisProgress(`${status.message || '处理中...'} (${status.progress}%)`)
        } else {
          setAnalysisProgress(status.message || '处理中...')
        }

        // 检查任务状态
        if (status.status === 'completed') {
          completed = true
          setAnalysisMessage({ type: 'success', text: '分析完成' })

          // 刷新论文数据
          const updatedPaper = await fetchPaperDetail(id)
          setPaper(updatedPaper)
        } else if (status.status === 'failed') {
          completed = true
          setAnalysisMessage({ type: 'error', text: `分析失败: ${status.error || '未知错误'}` })
        }
      }
    } catch (err) {
      // 检查是否是取消导致的错误
      if (err.name === 'AbortError') {
        setAnalysisMessage({ type: 'error', text: '分析已取消' })
      } else {
        setAnalysisMessage({ type: 'error', text: `分析失败: ${err.message}` })
      }
    } finally {
      setAnalyzing(false)
      setAnalysisProgress('')
      abortControllerRef.current = null
    }
  }

  // 组件卸载时清理定时器和取消请求
  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current)
      }
      // 取消正在进行的分析请求
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  // 格式化中文日期
  const formatChineseDate = (dateStr) => {
    if (!dateStr) return '未知'
    return format(new Date(dateStr), 'yyyy年M月d日', { locale: zhCN })
  }

  // 导出思维导图（接收 paper 对象作为参数，因为函数定义位置早于解构）
  const downloadOutline = (format, paperData) => {
    const outline = paperData?.analysis_json?.outline
    const paperTitle = paperData?.title
    if (!outline) return

    let content = ''
    const filename = `思维导图_${paperTitle?.slice(0, 30) || 'paper'}`

    if (format === 'json') {
      content = JSON.stringify(outline, null, 2)
      const blob = new Blob([content], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filename}.json`
      a.click()
      URL.revokeObjectURL(url)
    } else if (format === 'markdown') {
      // 递归生成 Markdown
      const generateMarkdown = (items, level = 1) => {
        let md = ''
        const prefix = '#'.repeat(level + 1)
        for (const item of items) {
          md += `${prefix} ${item.title}\n`
          if (item.children && item.children.length > 0) {
            md += generateMarkdown(item.children, level + 1)
          }
        }
        return md
      }
      content = `# ${paperTitle || '论文思维导图'}\n\n${generateMarkdown(outline)}`
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filename}.md`
      a.click()
      URL.revokeObjectURL(url)
    }
  }

  // 格式化简短日期
  const formatShortDate = (dateStr) => {
    if (!dateStr) return '未知'
    return format(new Date(dateStr), 'yyyy-MM-dd')
  }

  // 加载中
  if (loading) {
    return <PaperDetailSkeleton />
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
          <div className="flex justify-between items-center mb-4 pb-2 border-b border-gray-200">
            <h2 className="text-xl font-bold">
              思维导图
            </h2>
            {analysis_json?.outline && (
              <div className="flex gap-2">
                <button
                  onClick={() => downloadOutline('markdown', paper)}
                  className="text-sm px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  导出 Markdown
                </button>
                <button
                  onClick={() => downloadOutline('json', paper)}
                  className="text-sm px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  导出 JSON
                </button>
              </div>
            )}
          </div>
          {analysis_json?.outline ? (
            <OutlineTree outline={analysis_json.outline} paperTitle={title} />
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
              {(analysis_json.key_contributions || analysis_json.main_contributions) && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">
                    主要贡献
                  </h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.key_contributions || analysis_json.main_contributions)
                      ? (analysis_json.key_contributions || analysis_json.main_contributions)
                      : [(analysis_json.key_contributions || analysis_json.main_contributions)]
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
              {(analysis_json.weaknesses || analysis_json.limitations) && (
                <div>
                  <h3 className="text-sm font-bold text-gray-500 mb-2">不足</h3>
                  <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                    {(Array.isArray(analysis_json.weaknesses || analysis_json.limitations)
                      ? (analysis_json.weaknesses || analysis_json.limitations)
                      : [(analysis_json.weaknesses || analysis_json.limitations)]
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

        {/* 卡片6：相关工作与参考文献 */}
        {has_analysis && analysis_json?.related_work && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-xl font-bold mb-4 pb-2 border-b border-gray-200">
              相关工作与参考文献
            </h2>

            {/* 关键参考文献 */}
            {analysis_json.related_work.key_references &&
             analysis_json.related_work.key_references.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-500 mb-3">
                  📚 关键参考文献
                </h3>
                <div className="space-y-3">
                  {analysis_json.related_work.key_references.map((ref, i) => (
                    <div key={i} className="bg-gray-50 rounded-lg p-3">
                      <p className="font-medium text-gray-900 text-sm">
                        {ref.title}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {ref.authors} · {ref.year}
                      </p>
                      {ref.contribution && (
                        <p className="text-xs text-purple-700 mt-2 italic">
                          ↳ {ref.contribution}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 相似研究方向 */}
            {analysis_json.related_work.similar_papers &&
             analysis_json.related_work.similar_papers.length > 0 && (
              <div>
                <h3 className="text-sm font-bold text-gray-500 mb-3">
                  🔗 相似研究方向
                </h3>
                <div className="flex flex-wrap gap-2">
                  {analysis_json.related_work.similar_papers.map((topic, i) => (
                    <span
                      key={i}
                      className="px-3 py-1.5 bg-purple-50 text-purple-700 rounded-full text-sm"
                    >
                      {topic}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// 思维导图组件 - 使用 simple-mind-map
function OutlineTree({ outline, paperTitle }) {
  const containerRef = useRef(null)
  const wrapperRef = useRef(null)
  const mindMapRef = useRef(null)
  const isInitializingRef = useRef(false)
  const [mindMapError, setMindMapError] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    if (!outline || !containerRef.current || isInitializingRef.current) return

    setMindMapError(null)
    isInitializingRef.current = true

    // 使用 setTimeout 确保 DOM 已渲染
    const initTimer = setTimeout(() => {
      try {
        // 确保容器有尺寸
        const rect = containerRef.current?.getBoundingClientRect()

        if (!rect || rect.width <= 0 || rect.height <= 0) {
          console.warn('MindMap container has zero dimensions')
          setMindMapError('容器尺寸无效')
          isInitializingRef.current = false
          return
        }

        // 转换数据格式
        const items = Array.isArray(outline) ? outline : [outline]
        const mindData = convertToSimpleMindMapData(items, paperTitle)

        console.log('MindMap data:', JSON.stringify(mindData, null, 2))

        // 清理旧实例
        if (mindMapRef.current) {
          mindMapRef.current.destroy()
          mindMapRef.current = null
        }

        // 清空容器内容
        if (containerRef.current) {
          containerRef.current.innerHTML = ''
        }

        // 创建新实例 - 固定中心，只允许缩放
        mindMapRef.current = new MindMap({
          el: containerRef.current,
          data: mindData,
          readonly: true,
          layout: 'mindMap', // 经典思维导图布局：左右对称展开
          theme: 'default',
          fit: true,
          // 连线样式：贝塞尔曲线
          lineStyle: 'curve',
          // 节点样式配置
          nodeStyle: {
            radius: 8,
            paddingX: 14,
            paddingY: 8,
            fontSize: 15,
          },
          // 完全禁用拖拽
          isDisableDrag: true,
          // 禁用鼠标滚轮操作
          disableMouseWheelZoom: true,
          mousewheelAction: '',
          // 阻止默认事件
          mousedownEventPreventDefault: true,
        })

        console.log('MindMap created successfully')

        // 初始自适应
        setTimeout(() => {
          if (mindMapRef.current && mindMapRef.current.view) {
            mindMapRef.current.view.fit()
          }
        }, 100)
      } catch (err) {
        console.error('MindMap initialization error:', err)
        setMindMapError(err.message || String(err))
        isInitializingRef.current = false
      }
    }, 100)

    return () => {
      clearTimeout(initTimer)
      if (mindMapRef.current) {
        try {
          mindMapRef.current.destroy()
        } catch (e) {
          console.error('MindMap destroy error:', e)
        }
        mindMapRef.current = null
      }
      isInitializingRef.current = false
    }
  }, [outline, paperTitle])

  // 监听全屏变化
  useEffect(() => {
    const handleFullscreenChange = () => {
      const fullscreen = !!document.fullscreenElement
      setIsFullscreen(fullscreen)
      // 全屏状态变化时重新调整
      setTimeout(() => {
        if (mindMapRef.current && mindMapRef.current.view) {
          mindMapRef.current.view.fit()
        }
      }, 100)
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
    }
  }, [])

  // 重置视角 - 居中并自适应
  const handleResetView = () => {
    if (mindMapRef.current) {
      mindMapRef.current.view.fit()
    }
  }

  // 放大 - 以中心为基准
  const handleZoomIn = () => {
    if (mindMapRef.current) {
      const view = mindMapRef.current.view
      view.enlarge()
    }
  }

  // 缩小 - 以中心为基准
  const handleZoomOut = () => {
    if (mindMapRef.current) {
      const view = mindMapRef.current.view
      view.narrow()
    }
  }

  // 切换全屏
  const handleToggleFullscreen = async () => {
    if (!wrapperRef.current) return

    try {
      if (!document.fullscreenElement) {
        await wrapperRef.current.requestFullscreen()
      } else {
        await document.exitFullscreen()
      }
    } catch (err) {
      console.error('Fullscreen error:', err)
    }
  }

  if (!outline) return null

  return (
    <div>
      {/* 控制按钮 */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={handleZoomIn}
          className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="放大"
        >
          🔍+
        </button>
        <button
          onClick={handleZoomOut}
          className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="缩小"
        >
          🔍-
        </button>
        <button
          onClick={handleResetView}
          className="px-3 py-1.5 text-sm bg-purple-100 hover:bg-purple-200 text-purple-700 rounded transition-colors"
          title="居中显示"
        >
          🎯 居中显示
        </button>
        <button
          onClick={handleToggleFullscreen}
          className="px-3 py-1.5 text-sm bg-blue-100 hover:bg-blue-200 text-blue-700 rounded transition-colors"
          title={isFullscreen ? '退出全屏' : '全屏查看'}
        >
          {isFullscreen ? '🗴 退出全屏' : '⛶ 全屏查看'}
        </button>
      </div>

      {/* MindMap 容器 */}
      <div
        ref={wrapperRef}
        className={`mindmap-wrapper ${isFullscreen ? 'bg-white p-4' : ''}`}
        style={isFullscreen ? { height: '100vh', overflow: 'hidden' } : { overflow: 'hidden' }}
      >
        {isFullscreen && (
          <div className="absolute top-4 right-4 z-10 flex gap-2">
            <button
              onClick={handleZoomIn}
              className="px-3 py-1.5 text-sm bg-white/90 hover:bg-white shadow rounded transition-colors"
            >
              🔍+
            </button>
            <button
              onClick={handleZoomOut}
              className="px-3 py-1.5 text-sm bg-white/90 hover:bg-white shadow rounded transition-colors"
            >
              🔍-
            </button>
            <button
              onClick={handleResetView}
              className="px-3 py-1.5 text-sm bg-purple-100/90 hover:bg-purple-100 shadow text-purple-700 rounded transition-colors"
            >
              🎯 居中
            </button>
            <button
              onClick={handleToggleFullscreen}
              className="px-3 py-1.5 text-sm bg-gray-100/90 hover:bg-gray-100 shadow rounded transition-colors"
            >
              ✕ 关闭
            </button>
          </div>
        )}
        <div
          ref={containerRef}
          className="mindmap-container border border-gray-200 rounded-lg overflow-hidden"
          style={{ width: '100%', height: isFullscreen ? 'calc(100vh - 60px)' : '500px' }}
        />
      </div>

      {/* 错误提示和备用显示 */}
      {mindMapError && (
        <div className="mt-4">
          <div className="p-2 bg-yellow-50 text-yellow-700 text-sm rounded mb-2">
            思维导图加载失败: {mindMapError}
          </div>
          <div className="p-4 bg-gray-50 rounded-lg">
            <OutlineTreeView outline={outline} paperTitle={paperTitle} />
          </div>
        </div>
      )}
    </div>
  )
}

// 备用树形显示组件
function OutlineTreeView({ outline, paperTitle }) {
  const items = Array.isArray(outline) ? outline : [outline]
  const isFlatStringList = items.length > 0 && typeof items[0] === 'string'

  if (isFlatStringList) {
    return (
      <div className="space-y-1">
        <div className="font-bold text-purple-700 mb-2">{paperTitle || '论文大纲'}</div>
        {items.map((item, index) => {
          const text = typeof item === 'string' ? item.trim() : ''
          const indentLevel = typeof item === 'string' ? (item.length - item.trimStart().length) : 0
          const isMainChapter = text.match(/^\d+[.、\s]/)

          return (
            <div
              key={index}
              style={{ paddingLeft: `${indentLevel * 16 + 8}px` }}
              className={`py-0.5 ${isMainChapter ? 'font-semibold text-gray-800' : 'text-gray-600'}`}
            >
              {isMainChapter && <span className="text-purple-600 mr-1">●</span>}
              {text}
            </div>
          )
        })}
      </div>
    )
  }

  // 嵌套对象格式
  return (
    <div className="space-y-1">
      <div className="font-bold text-purple-700 mb-2">{paperTitle || '论文大纲'}</div>
      {items.map((item, index) => (
        <OutlineNode key={index} item={item} />
      ))}
    </div>
  )
}

function OutlineNode({ item, level = 0 }) {
  if (typeof item === 'string') {
    return (
      <div style={{ paddingLeft: `${level * 16}px` }} className="py-0.5 text-gray-600">
        {item}
      </div>
    )
  }

  const title = item.title || ''
  const children = item.children || []
  const isMainChapter = level === 0

  return (
    <div>
      <div
        style={{ paddingLeft: `${level * 16}px` }}
        className={`py-0.5 ${isMainChapter ? 'font-semibold text-gray-800 mt-1' : 'text-gray-600'}`}
      >
        {isMainChapter ? (
          <span className="text-purple-600 mr-1">●</span>
        ) : (
          <span className="text-gray-400 mr-1">○</span>
        )}
        {title}
      </div>
      {children.map((child, index) => (
        <OutlineNode key={index} item={child} level={level + 1} />
      ))}
    </div>
  )
}

// 分支颜色调色板（学术风格，柔和且有区分度）
const BRANCH_COLORS = [
  '#6366f1', // 紫色 - 引言
  '#8b5cf6', // 紫罗兰 - 相关工作
  '#06b6d4', // 青色 - 方法
  '#10b981', // 翠绿 - 实验
  '#f59e0b', // 琥珀 - 讨论
  '#ef4444', // 红色 - 结论
  '#ec4899', // 粉色 - 其他
  '#64748b', // 石板灰 - 备用
]

// 转换数据为 simple-mind-map 格式
// 支持分支颜色编码和贝塞尔曲线
function convertToSimpleMindMapData(items, paperTitle) {
  const isFlatStringList = items.length > 0 && typeof items[0] === 'string'

  let children = []

  if (isFlatStringList) {
    // 智能解析扁平列表
    children = parseFlatOutlineToChildren(items)
  } else {
    // 已经是嵌套对象格式，为每个顶级分支分配颜色
    children = items.map((item, index) => {
      const color = BRANCH_COLORS[index % BRANCH_COLORS.length]
      return convertNodeToSimpleMindMap(item, color)
    })
  }

  // 直接返回节点数据，不需要 root 包装
  return {
    data: {
      text: paperTitle || '论文大纲'
    },
    children: children
  }
}

// 解析扁平列表为 simple-mind-map children 格式
// 为每个主章节分配不同的颜色
function parseFlatOutlineToChildren(items) {
  const mainChapters = []
  let currentChapter = null
  let currentSubChapter = null
  let chapterIndex = 0

  items.forEach(item => {
    const text = typeof item === 'string' ? item : ''
    if (!text) return

    const trimmedText = text.trim()
    const indentLevel = text.length - text.trimStart().length

    // 检测主章节：数字开头，如 "1. 引言" 或 "1 引言"
    const mainMatch = trimmedText.match(/^(\d+)[.、\s]+(.+)/)

    // 检测二级章节：如 "2.1 预备知识"
    const subNumMatch = trimmedText.match(/^(\d+)\.(\d+)[.、\s]*(.+)/)

    // 检测带破折号的子章节：如 "- 研究动机"
    const dashMatch = trimmedText.match(/^[-–—•·]\s*(.+)/)

    if (mainMatch && !subNumMatch) {
      // 主章节 - 分配颜色
      if (currentSubChapter && currentChapter) {
        currentChapter.children.push(currentSubChapter)
        currentSubChapter = null
      }
      if (currentChapter) {
        mainChapters.push(currentChapter)
      }
      const color = BRANCH_COLORS[chapterIndex % BRANCH_COLORS.length]
      chapterIndex++
      currentChapter = {
        data: { text: mainMatch[2].trim(), color: color },
        children: [],
        _branchColor: color // 保存颜色供子节点继承
      }
    } else if (subNumMatch) {
      // 二级章节 (如 2.1) - 继承父章节颜色
      if (currentSubChapter && currentChapter) {
        currentChapter.children.push(currentSubChapter)
      }
      const branchColor = currentChapter?._branchColor || null
      currentSubChapter = {
        data: { text: subNumMatch[3].trim(), color: branchColor },
        children: [],
        _branchColor: branchColor
      }
    } else if (dashMatch && indentLevel > 0) {
      // 带破折号的子章节 - 继承颜色
      const subText = dashMatch[1].trim()
      const branchColor = currentChapter?._branchColor || currentSubChapter?._branchColor || null
      const node = { data: { text: subText, color: branchColor }, children: [] }
      if (currentSubChapter) {
        currentSubChapter.children.push(node)
      } else if (currentChapter) {
        currentChapter.children.push(node)
      }
    } else if (trimmedText && indentLevel > 0) {
      // 其他缩进内容作为子节点 - 继承颜色
      const branchColor = currentChapter?._branchColor || currentSubChapter?._branchColor || null
      const node = { data: { text: trimmedText, color: branchColor }, children: [] }
      if (currentSubChapter) {
        currentSubChapter.children.push(node)
      } else if (currentChapter) {
        currentChapter.children.push(node)
      }
    }
  })

  // 收尾
  if (currentSubChapter && currentChapter) {
    currentChapter.children.push(currentSubChapter)
  }
  if (currentChapter) {
    mainChapters.push(currentChapter)
  }

  // 清理临时属性
  const cleanNode = (node) => {
    const clean = { data: { ...node.data }, children: node.children.map(cleanNode) }
    return clean
  }

  return mainChapters.length > 0 ? mainChapters.map(cleanNode) : items.map((s, i) => ({
    data: { text: typeof s === 'string' ? s.trim() : s, color: BRANCH_COLORS[i % BRANCH_COLORS.length] },
    children: []
  }))
}

// 转换嵌套对象为 simple-mind-map 格式
// color 参数用于为整个分支着色（同一一级分支下的所有节点同色）
function convertNodeToSimpleMindMap(item, branchColor = null) {
  if (typeof item === 'string') {
    return { data: { text: item, color: branchColor }, children: [] }
  }
  return {
    data: { text: item.title || '', color: branchColor },
    children: (item.children || []).map(child => convertNodeToSimpleMindMap(child, branchColor))
  }
}