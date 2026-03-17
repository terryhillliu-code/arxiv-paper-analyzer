import { useState } from 'react'
import { Filter, ChevronDown, ChevronUp, X, Tag, Calendar } from 'lucide-react'

// 学科分类配置
const CATEGORIES = [
  { id: 'cs.AI', name: '人工智能' },
  { id: 'cs.LG', name: '机器学习' },
  { id: 'cs.CL', name: '计算语言学' },
  { id: 'cs.CV', name: '计算机视觉' },
  { id: 'cs.NE', name: '神经网络' },
  { id: 'cs.RO', name: '机器人' },
  { id: 'cs.DB', name: '数据库' },
  { id: 'cs.DC', name: '分布式计算' },
  { id: 'cs.SE', name: '软件工程' },
  { id: 'cs.CR', name: '密码学与安全' },
  { id: 'stat.ML', name: '统计机器学习' },
]

// 预设标签
const PRESET_TAGS = [
  '大模型', 'Transformer', '多模态', 'RAG', 'Agent',
  '微调技术', '提示工程', '向量数据库', '知识图谱', '推理优化',
  '模型压缩', 'RLHF', '代码生成', 'AI安全', '评测基准',
  '数据合成', '高效训练', '长文本', '具身智能', 'AI应用'
]

// 排序选项
const SORT_OPTIONS = [
  { value: 'published_desc', label: '最新发布' },
  { value: 'published_asc', label: '最早发布' },
  { value: 'views_desc', label: '最多浏览' },
]

export default function FilterBar({ filters = {}, onFilterChange, totalResults = 0 }) {
  const [isExpanded, setIsExpanded] = useState(false)

  // 解析当前筛选值
  const selectedCategories = filters.categories ? filters.categories.split(',').filter(Boolean) : []
  const selectedTags = filters.tags ? filters.tags.split(',').filter(Boolean) : []

  // 切换分类
  const toggleCategory = (categoryId) => {
    const newCategories = selectedCategories.includes(categoryId)
      ? selectedCategories.filter(c => c !== categoryId)
      : [...selectedCategories, categoryId]
    onFilterChange?.({ categories: newCategories.join(',') || null })
  }

  // 切换标签
  const toggleTag = (tag) => {
    const newTags = selectedTags.includes(tag)
      ? selectedTags.filter(t => t !== tag)
      : [...selectedTags, tag]
    onFilterChange?.({ tags: newTags.join(',') || null })
  }

  // 更新日期
  const handleDateChange = (field, value) => {
    onFilterChange?.({ [field]: value || null })
  }

  // 更新排序
  const handleSortChange = (e) => {
    onFilterChange?.({ sort_by: e.target.value || null })
  }

  // 移除单个筛选项
  const removeFilter = (type, value) => {
    if (type === 'category') {
      const newCategories = selectedCategories.filter(c => c !== value)
      onFilterChange?.({ categories: newCategories.join(',') || null })
    } else if (type === 'tag') {
      const newTags = selectedTags.filter(t => t !== value)
      onFilterChange?.({ tags: newTags.join(',') || null })
    } else if (type === 'date') {
      onFilterChange?.({ [value]: null })
    }
  }

  // 清除所有筛选
  const clearAllFilters = () => {
    onFilterChange?.({
      categories: null,
      tags: null,
      date_from: null,
      date_to: null,
      sort_by: null,
    })
  }

  // 计算是否有筛选
  const hasFilters = selectedCategories.length > 0 ||
    selectedTags.length > 0 ||
    filters.date_from ||
    filters.date_to

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      {/* 头部 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2 text-gray-700">
          <Filter size={18} />
          <span className="font-medium">筛选</span>
          {hasFilters && (
            <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
              已选 {selectedCategories.length + selectedTags.length + (filters.date_from ? 1 : 0) + (filters.date_to ? 1 : 0)} 项
            </span>
          )}
        </div>
        {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      {/* 折叠面板 */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-100">
          {/* 学科分类 */}
          <div>
            <h4 className="text-sm font-medium text-gray-600 mb-2">学科分类</h4>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => toggleCategory(cat.id)}
                  className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                    selectedCategories.includes(cat.id)
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-gray-50 text-gray-700 border-gray-200 hover:border-blue-300 hover:bg-blue-50'
                  }`}
                >
                  <span className="font-mono text-xs">{cat.id}</span>
                  <span className="ml-1">{cat.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 主题标签 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Tag size={14} className="text-gray-500" />
              <h4 className="text-sm font-medium text-gray-600">主题标签</h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {PRESET_TAGS.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    selectedTags.includes(tag)
                      ? 'bg-purple-600 text-white border-purple-600'
                      : 'bg-gray-50 text-gray-700 border-gray-200 hover:border-purple-300 hover:bg-purple-50'
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          {/* 日期范围 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Calendar size={14} className="text-gray-500" />
              <h4 className="text-sm font-medium text-gray-600">发布日期</h4>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="date"
                value={filters.date_from || ''}
                onChange={(e) => handleDateChange('date_from', e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              />
              <span className="text-gray-400">至</span>
              <input
                type="date"
                value={filters.date_to || ''}
                onChange={(e) => handleDateChange('date_to', e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* 排序方式 */}
          <div>
            <h4 className="text-sm font-medium text-gray-600 mb-2">排序方式</h4>
            <select
              value={filters.sort_by || ''}
              onChange={handleSortChange}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 bg-white"
            >
              <option value="">默认排序</option>
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* 已选筛选项 + 结果统计 */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {/* 已选分类 */}
          {selectedCategories.map((catId) => {
            const cat = CATEGORIES.find(c => c.id === catId)
            return (
              <span
                key={catId}
                className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded-full"
              >
                {cat?.name || catId}
                <button onClick={() => removeFilter('category', catId)}>
                  <X size={12} />
                </button>
              </span>
            )
          })}

          {/* 已选标签 */}
          {selectedTags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded-full"
            >
              {tag}
              <button onClick={() => removeFilter('tag', tag)}>
                <X size={12} />
              </button>
            </span>
          ))}

          {/* 已选日期 */}
          {filters.date_from && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
              从 {filters.date_from}
              <button onClick={() => removeFilter('date', 'date_from')}>
                <X size={12} />
              </button>
            </span>
          )}
          {filters.date_to && (
            <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full">
              至 {filters.date_to}
              <button onClick={() => removeFilter('date', 'date_to')}>
                <X size={12} />
              </button>
            </span>
          )}

          {/* 清除所有 */}
          {hasFilters && (
            <button
              onClick={clearAllFilters}
              className="text-sm text-gray-500 hover:text-red-600 transition-colors"
            >
              清除全部
            </button>
          )}
        </div>

        {/* 结果统计 */}
        <span className="text-sm text-gray-500">
          共 <span className="font-medium text-gray-700">{totalResults}</span> 条结果
        </span>
      </div>
    </div>
  )
}