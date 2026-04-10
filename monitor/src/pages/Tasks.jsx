import { useAPI } from '../components/hooks'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { ErrorMessage, LoadingSpinner } from '../components/ErrorBoundary'

const COLORS = ['#00d4ff', '#00ff88', '#ffaa00', '#ff4444', '#8884d8', '#82ca9d']

export default function Tasks() {
  const { data, loading, error, lastUpdate } = useAPI('/tasks/deep')

  if (error) return <ErrorMessage message={error} />
  if (loading) return <LoadingSpinner />

  const statusDistribution = data.status_distribution || {}
  const typeStatusDistribution = data.type_status_distribution || {}
  const failedTasks = data.failed_tasks || []
  const timeoutTasks = data.timeout_tasks || []

  // 状态分布饼图数据
  const pieData = Object.entries(statusDistribution).map(([name, value]) => ({ name, value }))

  // 任务类型柱状图数据
  const barData = Object.entries(typeStatusDistribution).map(([type, statusMap]) => ({
    type,
    pending: statusMap.pending || 0,
    running: statusMap.running || 0,
    completed: statusMap.completed || 0,
  }))

  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-500">最后更新: {lastUpdate}</div>

      {/* Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card text-center">
          <div className="text-sm text-gray-400">待处理</div>
          <div className="text-2xl font-bold text-arxiv-warning">{statusDistribution.pending || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">运行中</div>
          <div className="text-2xl font-bold text-arxiv-primary">{statusDistribution.running || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">已完成</div>
          <div className="text-2xl font-bold text-arxiv-secondary">{statusDistribution.completed || 0}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">失败</div>
          <div className="text-2xl font-bold text-arxiv-error">{statusDistribution.failed || 0}</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Status Distribution Pie */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">状态分布</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  fill="#8884d8"
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Task Type Bar */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">任务类型分布</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData}>
                <XAxis dataKey="type" stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
                <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#16213e', border: '1px solid #333' }}
                />
                <Legend />
                <Bar dataKey="pending" fill="#ffaa00" name="待处理" />
                <Bar dataKey="running" fill="#00d4ff" name="运行中" />
                <Bar dataKey="completed" fill="#00ff88" name="已完成" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Timeout Tasks */}
      {timeoutTasks.length > 0 && (
        <div className="card">
          <h3 className="text-sm text-arxiv-warning uppercase mb-4">⚠️ 超时任务 ({timeoutTasks.length}个)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-700">
                  <th className="px-2 py-2">任务ID</th>
                  <th className="px-2 py-2">类型</th>
                  <th className="px-2 py-2">开始时间</th>
                </tr>
              </thead>
              <tbody>
                {timeoutTasks.map(t => (
                  <tr key={t.id} className="border-b border-gray-800">
                    <td className="px-2 py-2 text-arxiv-primary">{t.id}</td>
                    <td className="px-2 py-2 text-gray-400">{t.type}</td>
                    <td className="px-2 py-2 text-arxiv-warning">{t.started_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Failed Tasks */}
      {failedTasks.length > 0 && (
        <div className="card">
          <h3 className="text-sm text-arxiv-error uppercase mb-4">❌ 失败任务 ({failedTasks.length}个)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-700">
                  <th className="px-2 py-2">任务ID</th>
                  <th className="px-2 py-2">类型</th>
                  <th className="px-2 py-2">错误</th>
                  <th className="px-2 py-2">时间</th>
                </tr>
              </thead>
              <tbody>
                {failedTasks.map(t => (
                  <tr key={t.id} className="border-b border-gray-800">
                    <td className="px-2 py-2 text-arxiv-primary">{t.id}</td>
                    <td className="px-2 py-2 text-gray-400">{t.type}</td>
                    <td className="px-2 py-2 text-arxiv-error truncate max-w-xs">{t.error}</td>
                    <td className="px-2 py-2 text-gray-500">{t.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Average Duration */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-2">平均执行时长</h3>
        <div className="text-xl font-bold text-arxiv-primary">
          {data.avg_duration_hour?.toFixed(1) || 0} 秒
        </div>
        <div className="text-xs text-gray-500">最近1小时完成的任务</div>
      </div>
    </div>
  )
}