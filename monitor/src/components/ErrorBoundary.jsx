import { Component } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-arxiv-error/20 border border-arxiv-error rounded-xl p-6 text-center">
          <AlertTriangle className="w-12 h-12 text-arxiv-error mx-auto mb-4" />
          <h2 className="text-lg font-bold text-arxiv-error mb-2">出错了</h2>
          <p className="text-gray-400 mb-4">{this.state.error?.message || '未知错误'}</p>
          <button
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-arxiv-card rounded-lg hover:bg-arxiv-card-dark transition"
          >
            <RefreshCw className="w-4 h-4" />
            刷新页面
          </button>
        </div>
      )
    }

    return this.props.children
  }
}

// 错误提示组件
export function ErrorMessage({ message, onRetry }) {
  return (
    <div className="bg-arxiv-card border border-arxiv-error/50 rounded-xl p-4">
      <div className="flex items-center gap-2 text-arxiv-error">
        <AlertTriangle className="w-5 h-5" />
        <span>加载失败: {message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-sm text-arxiv-primary hover:text-arxiv-secondary"
        >
          重试
        </button>
      )}
    </div>
  )
}

// 加载状态组件
export function LoadingSpinner({ message = '加载中...' }) {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-arxiv-primary"></div>
      <span className="ml-3 text-gray-400">{message}</span>
    </div>
  )
}