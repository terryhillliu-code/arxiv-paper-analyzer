import PropTypes from 'prop-types'
import { Activity, AlertTriangle, CheckCircle, Clock } from 'lucide-react'

const STATUS = {
  OK: 'ok',
  WARN: 'warn',
  ERROR: 'error',
  NEUTRAL: 'neutral',
}

const ICONS = {
  activity: Activity,
  alert: AlertTriangle,
  check: CheckCircle,
  clock: Clock,
}

export default function MetricCard({ title, value, subtitle, icon, status = STATUS.NEUTRAL, trend = null }) {
  const statusColors = {
    [STATUS.OK]: 'text-arxiv-secondary',
    [STATUS.WARN]: 'text-arxiv-warning',
    [STATUS.ERROR]: 'text-arxiv-error',
    [STATUS.NEUTRAL]: 'text-arxiv-primary',
  }

  const IconComponent = ICONS[icon] || Clock

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400 uppercase">{title}</span>
        <IconComponent className={`w-5 h-5 ${statusColors[status]}`} />
      </div>
      <div className={`text-3xl font-bold ${statusColors[status]}`}>
        {value}
      </div>
      {subtitle && (
        <div className="text-xs text-gray-500 mt-1">{subtitle}</div>
      )}
      {trend !== null && (
        <div className={`text-xs mt-2 ${trend > 0 ? 'text-arxiv-secondary' : 'text-arxiv-error'}`}>
          {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
        </div>
      )}
    </div>
  )
}

MetricCard.propTypes = {
  title: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  subtitle: PropTypes.string,
  icon: PropTypes.oneOf(['activity', 'alert', 'check', 'clock']),
  status: PropTypes.oneOf(Object.values(STATUS)),
  trend: PropTypes.number,
}

export { STATUS }