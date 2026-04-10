import { useAPI } from '../components/hooks'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { ErrorMessage, LoadingSpinner } from '../components/ErrorBoundary'

const COLORS = ['#00ff88', '#00d4ff', '#ffaa00', '#ff4444', '#8884d8']

export default function Quality() {
  const { data, loading, error, lastUpdate } = useAPI('/quality/trends')

  if (error) return <ErrorMessage message={error} />
  if (loading) return <LoadingSpinner />

  const tierDistribution = data.tier_distribution || {}
  const issueTypes = data.issue_types || {}
  const qualityStats = data.quality_stats || {}

  // Tier 柱状图数据
  const tierData = Object.entries(tierDistribution).map(([tier, count]) => ({
    tier,
    count,
  }))

  // Issue 饼图数据
  const issueData = Object.entries(issueTypes).slice(0, 6).map(([type, count]) => ({
    name: type,
    value: count,
  }))

  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-500">最后更新: {lastUpdate}</div>

      {/* Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card text-center">
          <div className="text-sm text-gray-400">已分析论文</div>
          <div className="text-2xl font-bold text-arxiv-secondary">{data.analyzed_total || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">Tier A</div>
          <div className="text-2xl font-bold text-arxiv-secondary">{tierDistribution.A || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">质量问题未解决</div>
          <div className="text-2xl font-bold text-arxiv-warning">{qualityStats.unresolved || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">解决率</div>
          <div className="text-2xl font-bold text-arxiv-primary">{data.resolution_rate || 0}%</div>
        </div>
      </div>

      {/* Tier Distribution */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">Tier 分布</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tierData}>
              <XAxis dataKey="tier" stroke="#666" tick={{ fill: '#666', fontSize: 14 }} />
              <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #333' }}
              />
              <Bar dataKey="count" fill="#00d4ff" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex gap-4">
          {tierData.map(t => (
            <div key={t.tier} className="text-sm">
              <span className={`font-bold ${t.tier === 'A' ? 'text-arxiv-secondary' : t.tier === 'B' ? 'text-arxiv-primary' : 'text-arxiv-warning'}`}>
                {t.tier}: {t.count}
              </span>
              <span className="text-gray-500 ml-1">
                ({((t.count / (data.analyzed_total || 1)) * 100).toFixed(1)}%)
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Issue Types */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">质量问题分布</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={issueData}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  {issueData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Issue List */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">问题类型详情</h3>
          <div className="space-y-2 overflow-y-auto max-h-64">
            {Object.entries(issueTypes).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between text-sm">
                <span className="text-gray-300 truncate">{type}</span>
                <span className={`font-bold ${count > 100 ? 'text-arxiv-error' : 'text-arxiv-warning'}`}>
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Analysis Mode */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">分析模式分布</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(data.analysis_mode || {}).map(([mode, count]) => (
            <div key={mode} className="bg-arxiv-card-dark rounded-lg p-3 text-center">
              <div className="text-xs text-gray-400">{mode || 'unknown'}</div>
              <div className="text-lg font-bold text-arxiv-primary">{count}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}