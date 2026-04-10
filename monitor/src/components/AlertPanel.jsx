import PropTypes from 'prop-types'
import { AlertTriangle, CheckCircle, Info } from 'lucide-react'

const STATUS = {
  OK: 'ok',
  WARN: 'warn',
  ERROR: 'error',
}

const STATUS_CONFIG = {
  [STATUS.OK]: {
    bg: 'bg-arxiv-secondary/20',
    border: 'border-arxiv-secondary',
    icon: CheckCircle,
    title: '✅ 系统运行正常'
  },
  [STATUS.WARN]: {
    bg: 'bg-arxiv-warning/20',
    border: 'border-arxiv-warning',
    icon: AlertTriangle,
    title: '⚠️ 需要注意'
  },
  [STATUS.ERROR]: {
    bg: 'bg-arxiv-error/20',
    border: 'border-arxiv-error',
    icon: AlertTriangle,
    title: '❌ 发现问题'
  },
}

export default function AlertPanel({ alerts, status = STATUS.OK }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG[STATUS.OK]

  const statusColor = status === STATUS.OK ? 'text-arxiv-secondary'
    : status === STATUS.WARN ? 'text-arxiv-warning'
    : 'text-arxiv-error'

  return (
    <div className={`${config.bg} ${config.border} border rounded-xl p-4`}>
      <div className="flex items-center gap-2 mb-2">
        <config.icon className={`w-5 h-5 ${statusColor}`} />
        <span className="font-medium">{config.title}</span>
      </div>
      {alerts && alerts.length > 0 && (
        <ul className="text-sm space-y-1">
          {alerts.map((alert, i) => (
            <li key={i} className="flex items-center gap-2">
              <Info className="w-3 h-3 text-gray-400" />
              {alert}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

AlertPanel.propTypes = {
  alerts: PropTypes.arrayOf(PropTypes.string),
  status: PropTypes.oneOf(Object.values(STATUS)),
}

export { STATUS }