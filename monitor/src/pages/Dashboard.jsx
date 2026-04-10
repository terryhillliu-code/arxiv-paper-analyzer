import { useMultiAPI } from '../components/hooks'
import MetricCard, { STATUS as CARD_STATUS } from '../components/MetricCard'
import AlertPanel, { STATUS as ALERT_STATUS } from '../components/AlertPanel'
import { ErrorMessage, LoadingSpinner } from '../components/ErrorBoundary'
import ProgressBar from '../components/ProgressBar'

export default function Dashboard() {
  const { data, loading, error, lastUpdate } = useMultiAPI({
    stats: '/stats',
    performance: '/performance',
    tasks: '/tasks/deep',
    quality: '/quality/trends',
  })

  if (error) return <ErrorMessage message={error} />
  if (loading) return <LoadingSpinner />

  const stats = data.stats || {}
  const perf = data.performance || {}
  const tasks = data.tasks || {}
  const quality = data.quality || {}
  const resources = perf.resources || {}

  // 检测问题
  const alerts = []
  if (tasks.timeout_count > 0) alerts.push(`有 ${tasks.timeout_count} 个任务超时`)
  if (tasks.status_distribution?.failed > 10) alerts.push(`失败任务过多: ${tasks.status_distribution.failed}个`)
  if (quality.quality_stats?.unresolved > 100) alerts.push(`质量问题待修复: ${quality.quality_stats.unresolved}个`)
  if (!perf.workers || perf.workers.length === 0) alerts.push('无 Worker 运行')
  if (resources.cpu_percent > 90) alerts.push(`CPU 使用率过高: ${resources.cpu_percent}%`)
  if (resources.memory_percent > 95) alerts.push(`内存使用率过高: ${resources.memory_percent}%`)

  const status = alerts.length === 0 ? ALERT_STATUS.OK
    : alerts.some(a => a.includes('过多') || a.includes('无')) ? ALERT_STATUS.ERROR
    : ALERT_STATUS.WARN

  return (
    <div className="space-y-4">
      {/* Alert Panel */}
      <AlertPanel alerts={alerts} status={status} />

      {/* Last Update */}
      <div className="text-xs text-gray-500">最后更新: {lastUpdate}</div>

      {/* Main Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="分析进度"
          value={`${stats.progress || 0}%`}
          subtitle={`${stats.analyzed || 0} / ${stats.total || 0}`}
          icon="check"
          status={CARD_STATUS.OK}
        />
        <MetricCard
          title="PDF覆盖率"
          value={`${stats.pdf_rate || 0}%`}
          subtitle={`${stats.pdf_count || 0} 个`}
          icon="activity"
          status={stats.pdf_rate > 90 ? CARD_STATUS.OK : CARD_STATUS.WARN}
        />
        <MetricCard
          title="待处理任务"
          value={tasks.status_distribution?.pending || stats.pending || 0}
          subtitle={`运行中: ${tasks.status_distribution?.running || stats.running || 0}`}
          icon="clock"
          status={(tasks.status_distribution?.pending || 0) > 100 ? CARD_STATUS.WARN : CARD_STATUS.OK}
        />
        <MetricCard
          title="质量问题"
          value={quality.quality_stats?.unresolved || 0}
          subtitle={`解决率: ${quality.resolution_rate || 0}%`}
          icon="alert"
          status={(quality.quality_stats?.unresolved || 0) > 100 ? CARD_STATUS.WARN : CARD_STATUS.OK}
        />
      </div>

      {/* Performance & Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* System Resources */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">系统资源</h3>
          <div className="space-y-4">
            <ProgressBar label="CPU" value={resources.cpu_percent} thresholds={{ warn: 70, error: 90 }} />
            <ProgressBar label="内存" value={resources.memory_percent} thresholds={{ warn: 85, error: 95 }} />
            <ProgressBar label="磁盘" value={resources.disk_percent} thresholds={{ warn: 80, error: 90 }} />
          </div>
        </div>

        {/* Workers */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">Worker 进程</h3>
          <div className="space-y-2">
            {perf.workers?.length > 0 ? (
              perf.workers.map(w => (
                <div key={w.pid} className="flex items-center justify-between text-sm">
                  <span className="text-arxiv-secondary">{w.name}</span>
                  <div className="flex gap-2">
                    <span className="text-gray-400">PID: {w.pid}</span>
                    <span className="text-gray-400">并发: {w.concurrent}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-arxiv-error text-sm">⚠️ 无 Worker 运行</div>
            )}
          </div>
        </div>

        {/* Tier Distribution */}
        <div className="card">
          <h3 className="text-sm text-gray-400 uppercase mb-4">Tier 分布</h3>
          <div className="space-y-2">
            {Object.entries(quality.tier_distribution || {}).map(([tier, count]) => (
              <div key={tier} className="flex items-center justify-between">
                <span className={`font-bold ${tier === 'A' ? 'text-arxiv-secondary' : tier === 'B' ? 'text-arxiv-primary' : 'text-arxiv-warning'}`}>
                  {tier}
                </span>
                <span className="text-gray-300">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Task Type Distribution */}
      <div className="card">
        <h3 className="text-sm text-gray-400 uppercase mb-4">任务类型分布</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(tasks.type_status_distribution || {}).map(([type, statusMap]) => (
            <div key={type} className="bg-arxiv-card-dark rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-2">{type}</div>
              <div className="text-sm space-y-1">
                {Object.entries(statusMap).map(([status, count]) => (
                  <div key={status} className="flex justify-between">
                    <span className="text-gray-500">{status}</span>
                    <span className={status === 'pending' ? 'text-arxiv-warning' : status === 'running' ? 'text-arxiv-primary' : 'text-gray-400'}>
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}