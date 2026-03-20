import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'

export default function AnalysisReport({ report }) {
  if (!report) {
    return (
      <div className="text-center py-12 text-gray-400">
        暂无分析报告
      </div>
    )
  }

  return (
    <div className="prose prose-slate max-w-none analysis-report">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeRaw]}
        components={{
          // 链接
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 underline"
            >
              {children}
            </a>
          ),
          // 标题
          h1: ({ children }) => (
            <h1 className="text-2xl font-bold text-gray-900 mt-6 mb-4 pb-2 border-b border-gray-200">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-bold text-gray-800 mt-5 mb-3">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-semibold text-gray-800 mt-4 mb-2">
              {children}
            </h3>
          ),
          // 表格
          table: ({ children }) => (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full border border-gray-300">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-100">{children}</thead>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 px-4 py-2 text-left font-semibold text-gray-700">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 px-4 py-2 text-gray-600">
              {children}
            </td>
          ),
          // 代码
          code: ({ className, children }) => {
            const isInline = !className
            if (isInline) {
              return (
                <code className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-sm font-mono">
                  {children}
                </code>
              )
            }
            return (
              <code className="block bg-gray-100 text-gray-800 p-4 rounded-lg overflow-x-auto text-sm font-mono">
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="bg-gray-100 rounded-lg my-4 overflow-hidden">
              {children}
            </pre>
          ),
          // 引用
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-gray-400 pl-4 py-2 my-4 bg-gray-50 text-gray-600 italic">
              {children}
            </blockquote>
          ),
          // 列表
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 my-3 text-gray-700">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 my-3 text-gray-700">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed">{children}</li>
          ),
          // 段落
          p: ({ children }) => (
            <p className="leading-relaxed my-3 text-gray-700">{children}</p>
          ),
          // 数学公式容器
          div: ({ className, children }) => {
            if (className?.includes('katex-display')) {
              return (
                <div className="my-4 overflow-x-auto">
                  {children}
                </div>
              )
            }
            return <div className={className}>{children}</div>
          },
        }}
      >
        {report}
      </ReactMarkdown>
    </div>
  )
}