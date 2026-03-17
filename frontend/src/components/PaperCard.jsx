import { Link } from 'react-router-dom'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import { ExternalLink, FileText, Eye, Sparkles } from 'lucide-react'

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

// 默认颜色
const DEFAULT_COLOR = { bg: 'bg-gray-100', text: 'text-gray-700', border: 'border-gray-200' }

export default function PaperCard({ paper }) {
  if (!paper) return null

  const {
    id,
    title,
    authors = [],
    categories = [],
    published_date,
    summary,
    tags = [],
    institution,
    arxiv_url,
    pdf_url,
    view_count = 0,
    has_deep_analysis = false,
  } = paper

  // 格式化日期
  const formattedDate = published_date
    ? format(new Date(published_date), 'yyyy-MM-dd', { locale: zhCN })
    : '未知日期'

  // 处理作者显示
  const displayAuthors = authors.slice(0, 5)
  const remainingCount = authors.length - 5

  // 处理分类显示（最多显示3个）
  const displayCategories = categories.slice(0, 3)

  // 处理标签显示（最多显示5个）
  const displayTags = tags.slice(0, 5)

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden transition-all duration-200 hover:shadow-lg hover:border-blue-300 group">
      {/* 顶部：分类 + 日期 */}
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <div className="flex flex-wrap gap-1.5">
          {displayCategories.map((cat) => {
            const colors = CATEGORY_COLORS[cat] || DEFAULT_COLOR
            return (
              <span
                key={cat}
                className={`px-2 py-0.5 text-xs font-medium rounded ${colors.bg} ${colors.text} ${colors.border} border`}
              >
                {cat}
              </span>
            )
          })}
        </div>
        <span className="text-xs text-gray-400">{formattedDate}</span>
      </div>

      {/* 标题 */}
      <Link to={`/paper/${id}`} className="block px-4 pb-2">
        <h3 className="text-lg font-semibold text-gray-900 line-clamp-2 group-hover:text-blue-600 transition-colors">
          {title}
        </h3>
      </Link>

      {/* 作者 */}
      <div className="px-4 pb-2">
        <p className="text-sm text-gray-500">
          {displayAuthors.map((author, idx) => (
            <span key={idx}>
              {author}
              {idx < displayAuthors.length - 1 && '、'}
            </span>
          ))}
          {remainingCount > 0 && (
            <span className="text-gray-400"> 等{remainingCount}人</span>
          )}
        </p>
      </div>

      {/* 机构 */}
      {institution && (
        <div className="px-4 pb-2">
          <p className="text-sm text-gray-500">
            <span className="text-gray-400">机构：</span>
            {institution}
          </p>
        </div>
      )}

      {/* 一句话总结 */}
      {summary && (
        <div className="px-4 pb-3">
          <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
            <p className="text-sm text-blue-800 line-clamp-3 leading-relaxed">
              {summary}
            </p>
          </div>
        </div>
      )}

      {/* 主题标签 */}
      {displayTags.length > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1.5">
          {displayTags.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* 底部操作栏 */}
      <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between bg-gray-50/50">
        <div className="flex items-center gap-3">
          {/* 深度分析按钮 */}
          <Link
            to={`/paper/${id}`}
            className={`inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              has_deep_analysis
                ? 'bg-green-100 text-green-700 hover:bg-green-200'
                : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
            }`}
          >
            <Sparkles size={14} />
            {has_deep_analysis ? '查看分析' : '深度分析'}
          </Link>

          {/* ArXiv 链接 */}
          {arxiv_url && (
            <a
              href={arxiv_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-blue-600 transition-colors"
            >
              <ExternalLink size={14} />
              ArXiv
            </a>
          )}

          {/* PDF 链接 */}
          {pdf_url && (
            <a
              href={pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-blue-600 transition-colors"
            >
              <FileText size={14} />
              PDF
            </a>
          )}
        </div>

        {/* 浏览量 */}
        <div className="flex items-center gap-1 text-sm text-gray-400">
          <Eye size={14} />
          <span>{view_count}</span>
        </div>
      </div>
    </div>
  )
}