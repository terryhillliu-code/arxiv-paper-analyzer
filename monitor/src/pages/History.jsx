import { useState } from 'react'
import { useAPI } from '../components/hooks'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar } from 'recharts'
import { format } from 'date-fns'
import { ErrorMessage, LoadingSpinner } from '../components/ErrorBoundary'

const TIME_RANGES = [
  { label: '1小时', hours: 1 },
  { label: '6小时', hours: 6 },
  { label: '24小时', hours: 24 },
  { label: '7天', hours: 168 },
]

export default function History() {
  const [timeRange, setTimeRange] = useState(24)
  const { data: metricsData, loading: metricsLoading, error: metricsError } = useAPI(`/history/metrics?hours=${timeRange}`)
  const { data: tasksData, loading: tasksLoading, error: tasksError } = useAPI(`/history/tasks?hours=${timeRange}`)

  if (metricsError || tasksError) return <ErrorMessage message={metricsError || tasksError} />
  if (metricsLoading || tasksLoading) return <LoadingSpinner />

  const cpuHistory = metricsData?.cpu_percent || []
  const memoryHistory = metricsData?.memory_percent || []
  const speedHistory = metricsData?.speed_hour || []
  const taskHistory = tasksData || []

  // 格式化时间
  const formatTime = (timestamp) => {
    try {
      const date = new Date(timestamp)
      return timeRange <= 24 ? format(date, 'HH:mm') : format(date, 'MM/dd HH:mm')
    } catch {
      return timestamp
    }
  }

  // 处理图表数据
  const cpuChartData = cpuHistory.map(d => ({ time: formatTime(d.timestamp), value: d.value }))
  const memoryChartData = memoryHistory.map(d => ({ time: formatTime(d.timestamp), value: d.value }))
  const speedChartData = speedHistory.map(d => ({ time: formatTime(d.timestamp), value: d.value }))
  const taskChartData = taskHistory.map(d => ({
    time: formatTime(d.timestamp),
    pending: d.pending,
    running: d.running,
    completed: d.completed,
    failed: d.failed,
  }))

  return (
    <div className="space-y-4">
      {/* Time Range Selector */}
      <div className="flex gap-2">
        {TIME_RANGES.map(range => (
          <button
            key={range.hours}
            onClick={() => setTimeRange(range.hours)}
            className={`px-4 py-2 rounded-lg text-sm ${
              timeRange === range.hours
                ? 'bg-arxiv-primary text-arxiv-dark'
                : 'bg-arxiv-card text-gray-400 hover:text-gray-200'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>

      {/* Speed Chart */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">处理速度趋势 (篇/分钟)</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={speedChartData}>
              <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} width={40} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #333' }}
                labelStyle={{ color: '#eee' }}
              />
              <Area type="monotone" dataKey="value" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Resource Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* CPU History */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">CPU 使用率历史</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cpuChartData}>
                <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} width={40} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ background: '#16213e', border: '1px solid #333' }}
                />
                <Line type="monotone" dataKey="value" stroke="#00ff88" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Memory History */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">内存使用率历史</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={memoryChartData}>
                <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} width={40} domain={[0, 100]} />
                <Tooltip
                  contentStyle={{ background: '#16213e', border: '1px solid #333' }}
                />
                <Line type="monotone" dataKey="value" stroke="#00d4ff" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Task Stats History */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">任务队列状态历史</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={taskChartData.slice(-20)}>
              <XAxis dataKey="time" stroke="#666" tick={{ fill: '#666', fontSize: 10 }} />
              <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#16213e', border: '1px solid #333' }}
              />
              <Bar dataKey="pending" fill="#ffaa00" name="待处理" stackId="a" />
              <Bar dataKey="running" fill="#00d4ff" name="运行中" stackId="a" />
              <Bar dataKey="completed" fill="#00ff88" name="已完成" stackId="b" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card text-center">
          <div className="text-sm text-gray-400">数据点数</div>
          <div className="text-xl font-bold text-arxiv-primary">{cpuChartData.length}</div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">平均 CPU</div>
          <div className="text-xl font-bold text-arxiv-secondary">
            {cpuChartData.length > 0
              ? (cpuChartData.reduce((sum, d) => sum + d.value, 0) / cpuChartData.length).toFixed(1)
              : 0}%
          </div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">平均内存</div>
          <div className="text-xl font-bold text-arxiv-primary">
            {memoryChartData.length > 0
              ? (memoryChartData.reduce((sum, d) => sum + d.value, 0) / memoryChartData.length).toFixed(1)
              : 0}%
          </div>
        </div>
        <div className="card text-center">
          <div className="text-sm text-gray-400">平均速度</div>
          <div className="text-xl font-bold text-arxiv-secondary">
            {speedChartData.length > 0
              ? (speedChartData.reduce((sum, d) => sum + d.value, 0) / speedChartData.length).toFixed(2)
              : 0}
          </div>
        </div>
      </div>
    </div>
  )
}