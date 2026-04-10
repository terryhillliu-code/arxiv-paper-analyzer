import { Link } from 'react-router-dom'
import { format } from 'date-fns'

// 学科分类颜色映射
const CATEGORY_COLORS = {
  // Tier 1 - 核心
  'cs.AI': 'bg-purple-100 text-purple-700',
  'cs.CL': 'bg-blue-100 text-blue-700',
  'cs.LG': 'bg-green-100 text-green-700',
  'cs.CV': 'bg-orange-100 text-orange-700',
  'cs.NE': 'bg-red-100 text-red-700',
  // Tier 2 - 重要扩展
  'cs.RO': 'bg-yellow-100 text-yellow-700',
  'cs.DC': 'bg-teal-100 text-teal-700',
  'cs.CR': 'bg-pink-100 text-pink-700',
  'cs.IR': 'bg-sky-100 text-sky-700',
  'cs.SE': 'bg-cyan-100 text-cyan-700',
  // Tier 3 - 关注
  'cs.HC': 'bg-indigo-100 text-indigo-700',
  'stat.ML': 'bg-emerald-100 text-emerald-700',
  'eess.AS': 'bg-violet-100 text-violet-700',
  'eess.IV': 'bg-amber-100 text-amber-700',
  // 其他
  'cs.DB': 'bg-slate-100 text-slate-700',
  'cs.AR': 'bg-rose-100 text-rose-700',
  'cs.NI': 'bg-lime-100 text-lime-700',
  'cs.MM': 'bg-fuchsia-100 text-fuchsia-700',
}

// 默认颜色
const DEFAULT_COLOR = 'bg-gray-100 text-gray-600'

// Tier 颜色映射
const TIER_COLORS = {
  'A': 'bg-red-500 text-white',
  'B': 'bg-yellow-500 text-white',
  'C': 'bg-gray-400 text-white',
}

export default function PaperCard({ paper, index }) {
  if (!paper) return null

  const {
    id,
    title,
    authors = [],
    categories = [],
    publish_date,
    summary,
    tags = [],
    institutions = [],
    has_analysis = false,
    tier,
  } = paper

  // 格式化日期
  const formattedDate = publish_date
    ? format(new Date(publish_date), 'yyyy-MM-dd')
    : '未知日期'

  // 处理作者显示（最多6个）
  const displayAuthors = authors.slice(0, 6)
  const hasMoreAuthors = authors.length > 6

  // 处理分类显示（最多显示4个）
  const displayCategories = categories.slice(0, 4)

  // 处理主题标签（取第一个）
  const mainTag = tags && tags.length > 0 ? tags[0] : null

  // 处理机构显示
  const displayInstitutions = institutions && institutions.length > 0 ? institutions.slice(0, 3) : []
  const hasMoreInstitutions = institutions && institutions.length > 3

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      {/* 顶部一行：序号 + 分类标签 + 主题标签 */}
      <div className="flex items-center gap-2 mb-3">
        {/* 序号 */}
        <span className="text-2xl text-gray-300 font-bold">
          {index}
        </span>

        {/* Tier 标签 */}
        {tier && (
          <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${TIER_COLORS[tier] || 'bg-gray-200 text-gray-600'}`}>
            {tier}
          </span>
        )}

        {/* 学科分类标签 */}
        <div className="flex flex-wrap gap-1.5">
          {displayCategories.map((cat) => (
            <span
              key={cat}
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                CATEGORY_COLORS[cat] || DEFAULT_COLOR
              }`}
            >
              {cat}
            </span>
          ))}
        </div>

        {/* 主题标签 */}
        {mainTag && (
          <span className="text-sm text-purple-700 ml-auto">
            {mainTag}
          </span>
        )}
      </div>

      {/* 标题行 */}
      <Link to={`/paper/${id}`} className="block mb-2">
        <h2 className="text-xl font-bold text-gray-900 hover:text-purple-700 transition-colors">
          {title}
        </h2>
      </Link>

      {/* 作者行 */}
      <p className="text-sm text-gray-600 mb-1">
        <span className="font-bold">作者：</span>
        {displayAuthors.map((author, idx) => (
          <span key={idx}>
            {author}
            {idx < displayAuthors.length - 1 && '、'}
          </span>
        ))}
        {hasMoreAuthors && <span>...</span>}
      </p>

      {/* 机构行 */}
      {displayInstitutions.length > 0 && (
        <p className="text-sm mb-1">
          <span className="font-bold">机构：</span>
          <span className="text-purple-700 font-bold italic">
            {displayInstitutions[0]}
          </span>
          {displayInstitutions.length > 1 && (
            <span className="text-gray-600">
              、{displayInstitutions.slice(1).join('、')}
            </span>
          )}
          {hasMoreInstitutions && <span className="text-gray-600">...</span>}
        </p>
      )}

      {/* 日期行 */}
      <p className="text-sm text-gray-600 mb-3">
        <span className="font-bold">日期：</span>
        {formattedDate}
      </p>

      {/* 一段话总结区域 */}
      {summary && (
        <div className="border-l-4 border-purple-500 bg-gray-50 pl-4 py-3 mb-4">
          <p className="text-xs text-gray-500 mb-1">一段话总结:</p>
          <p className="text-sm text-gray-700 leading-relaxed">
            {summary}
          </p>
        </div>
      )}

      {/* 底部：深度分析按钮 */}
      <Link
        to={`/paper/${id}`}
        className={`inline-block border rounded-lg px-4 py-2 text-sm transition-colors ${
          has_analysis
            ? 'border-purple-700 text-purple-700 hover:bg-purple-50'
            : 'border-gray-300 text-gray-600 hover:border-purple-700 hover:text-purple-700'
        }`}
      >
        {has_analysis ? '查看分析' : '深度分析'}
      </Link>
    </div>
  )
}