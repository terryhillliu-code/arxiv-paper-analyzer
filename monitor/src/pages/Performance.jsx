import { useAPI } from '../components/hooks'
import { ErrorMessage, LoadingSpinner } from '../components/ErrorBoundary'

export default function Performance() {
  const { data, loading, error, lastUpdate } = useAPI('/performance')

  if (error) return <ErrorMessage message={error} />
  if (loading) return <LoadingSpinner />

  const resources = data.resources || {}
  const workers = data.workers || []
  const queueStatus = data.queue_status || {}

  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-500">最后更新: {lastUpdate}</div>

      {/* Resource Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* CPU */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">CPU 使用率</h3>
          <div className="flex items-center justify-center">
            <div className="relative w-32 h-32">
              <svg viewBox="0 0 100 100" className="w-full h-full">
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke="#0f0f23"
                  strokeWidth="10"
                />
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke={resources.cpu_percent > 90 ? '#ff4444' : resources.cpu_percent > 70 ? '#ffaa00' : '#00ff88'}
                  strokeWidth="10"
                  strokeDasharray={`${resources.cpu_percent * 2.51} 251`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${resources.cpu_percent > 90 ? 'text-arxiv-error' : 'text-arxiv-secondary'}`}>
                  {resources.cpu_percent?.toFixed(0) || 0}%
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Memory */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">内存使用率</h3>
          <div className="flex items-center justify-center">
            <div className="relative w-32 h-32">
              <svg viewBox="0 0 100 100" className="w-full h-full">
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke="#0f0f23"
                  strokeWidth="10"
                />
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke={resources.memory_percent > 95 ? '#ff4444' : resources.memory_percent > 85 ? '#ffaa00' : '#00d4ff'}
                  strokeWidth="10"
                  strokeDasharray={`${resources.memory_percent * 2.51} 251`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${resources.memory_percent > 95 ? 'text-arxiv-error' : 'text-arxiv-primary'}`}>
                  {resources.memory_percent?.toFixed(0) || 0}%
                </span>
              </div>
            </div>
          </div>
          <div className="text-center text-xs text-gray-500 mt-2">
            {resources.memory_used_gb?.toFixed(1) || 0} / {resources.memory_total_gb?.toFixed(1) || 0} GB
          </div>
        </div>

        {/* Disk */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">磁盘使用率</h3>
          <div className="flex items-center justify-center">
            <div className="relative w-32 h-32">
              <svg viewBox="0 0 100 100" className="w-full h-full">
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke="#0f0f23"
                  strokeWidth="10"
                />
                <circle
                  cx="50" cy="50" r="40"
                  fill="none"
                  stroke={resources.disk_percent > 90 ? '#ff4444' : '#00d4ff'}
                  strokeWidth="10"
                  strokeDasharray={`${resources.disk_percent * 2.51} 251`}
                  strokeLinecap="round"
                  transform="rotate(-90 50 50)"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold text-arxiv-primary">
                  {resources.disk_percent?.toFixed(0) || 0}%
                </span>
              </div>
            </div>
          </div>
          <div className="text-center text-xs text-gray-500 mt-2">
            {resources.disk_used_gb?.toFixed(1) || 0} / {resources.disk_total_gb?.toFixed(1) || 0} GB
          </div>
        </div>
      </div>

      {/* Workers */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">Worker 进程状态</h3>
        {workers.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workers.map(w => (
              <div key={w.pid} className="bg-arxiv-card-dark rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-arxiv-secondary font-bold">{w.name}</span>
                  <span className="text-xs bg-arxiv-secondary/20 text-arxiv-secondary px-2 py-1 rounded">
                    运行中
                  </span>
                </div>
                <div className="text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-gray-400">PID</span>
                    <span className="text-gray-300">{w.pid}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">并发数</span>
                    <span className="text-arxiv-primary">{w.concurrent}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">CPU</span>
                    <span className="text-gray-300">{w.cpu}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">内存</span>
                    <span className="text-gray-300">{w.memory}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-arxiv-error text-center py-4">⚠️ 无 Worker 进程运行</div>
        )}
      </div>

      {/* Queue Status */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">队列状态</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Object.entries(queueStatus).map(([status, count]) => (
            <div key={status} className="bg-arxiv-card-dark rounded-lg p-3 text-center">
              <div className="text-xs text-gray-400">{status}</div>
              <div className={`text-xl font-bold ${status === 'pending' ? 'text-arxiv-warning' : status === 'running' ? 'text-arxiv-primary' : status === 'completed' ? 'text-arxiv-secondary' : 'text-arxiv-error'}`}>
                {count}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}