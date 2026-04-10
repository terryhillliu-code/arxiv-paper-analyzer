import PropTypes from 'prop-types'

export default function ProgressBar({
  value,
  label,
  thresholds = { warn: 70, error: 90 },
  showValue = true
}) {
  const getColor = () => {
    if (value >= thresholds.error) return 'bg-arxiv-error'
    if (value >= thresholds.warn) return 'bg-arxiv-warning'
    return 'bg-arxiv-secondary'
  }

  return (
    <div className="flex items-center justify-between">
      <span className="text-gray-400">{label}</span>
      <div className="flex items-center gap-2">
        <div className="w-20 h-2 bg-arxiv-card-dark rounded-full overflow-hidden">
          <div
            className={`h-full ${getColor()}`}
            style={{ width: `${value || 0}%` }}
          />
        </div>
        {showValue && (
          <span className="text-sm">{value?.toFixed(1) || 0}%</span>
        )}
      </div>
    </div>
  )
}

ProgressBar.propTypes = {
  value: PropTypes.number,
  label: PropTypes.string.isRequired,
  thresholds: PropTypes.shape({
    warn: PropTypes.number,
    error: PropTypes.number,
  }),
  showValue: PropTypes.bool,
}