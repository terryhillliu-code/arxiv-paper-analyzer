const API_BASE = '/api'

/**
 * 通用请求函数
 * 自动添加 Content-Type 头，处理错误响应
 */
async function request(path, options = {}) {
  const url = `${API_BASE}${path}`

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`HTTP ${response.status}: ${errorText}`)
  }

  return response.json()
}

/**
 * 获取论文列表
 * @param {Object} params - 查询参数
 * @param {string} params.search - 搜索关键词
 * @param {string} params.categories - 分类过滤
 * @param {string} params.tags - 标签过滤
 * @param {string} params.date_from - 起始日期
 * @param {string} params.date_to - 结束日期
 * @param {boolean} params.has_analysis - 是否有分析
 * @param {string} params.sort_by - 排序字段
 * @param {number} params.page - 页码
 * @param {number} params.page_size - 每页数量
 */
export async function fetchPapers(params = {}) {
  const searchParams = new URLSearchParams()

  // 只添加有值的参数
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, value)
    }
  })

  const queryString = searchParams.toString()
  const path = queryString ? `/papers?${queryString}` : '/papers'

  return request(path)
}

/**
 * 获取论文详情
 * @param {number|string} id - 论文ID
 */
export async function fetchPaperDetail(id) {
  return request(`/papers/${id}`)
}

/**
 * 触发从 ArXiv 拉取论文
 * @param {string} query - 搜索查询
 * @param {number} maxResults - 最大结果数
 */
export async function triggerFetch(query, maxResults = 10) {
  return request('/fetch', {
    method: 'POST',
    body: JSON.stringify({
      query,
      max_results: maxResults,
    }),
  })
}

/**
 * 批量生成论文摘要
 * @param {number} limit - 处理数量限制
 */
export async function generateSummaries(limit = 10) {
  return request(`/papers/generate-summaries?limit=${limit}`, {
    method: 'POST',
  })
}

/**
 * 分析单篇论文（深度分析）
 * @param {number|string} paperId - 论文ID
 * @param {boolean} forceRefresh - 是否强制刷新
 */
export async function analyzePaper(paperId, forceRefresh = false) {
  return request(`/papers/${paperId}/analyze?force_refresh=${forceRefresh}`, {
    method: 'POST',
  })
}

/**
 * 获取系统统计数据
 */
export async function fetchStats() {
  return request('/stats')
}

/**
 * 获取所有标签列表
 */
export async function fetchTags() {
  return request('/tags')
}

/**
 * 获取所有分类列表
 */
export async function fetchCategories() {
  return request('/categories')
}