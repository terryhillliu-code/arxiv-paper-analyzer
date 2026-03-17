import { useState } from 'react'
import { Search, X } from 'lucide-react'

export default function SearchBar({ value = '', onChange, placeholder = '搜索论文标题、摘要...' }) {
  const [localValue, setLocalValue] = useState(value)

  const handleSubmit = (e) => {
    e.preventDefault()
    onChange?.(localValue)
  }

  const handleClear = () => {
    setLocalValue('')
    onChange?.('')
  }

  const handleInputChange = (e) => {
    setLocalValue(e.target.value)
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative flex items-center bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* 左侧搜索图标 */}
        <div className="pl-4 text-gray-400">
          <Search size={20} />
        </div>

        {/* 输入框 */}
        <input
          type="text"
          value={localValue}
          onChange={handleInputChange}
          placeholder={placeholder}
          className="flex-1 px-3 py-3 outline-none text-gray-700 placeholder-gray-400"
        />

        {/* 清除按钮 */}
        {localValue && (
          <button
            type="button"
            onClick={handleClear}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={18} />
          </button>
        )}

        {/* 搜索按钮 */}
        <button
          type="submit"
          className="px-5 py-3 bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors"
        >
          搜索
        </button>
      </div>
    </form>
  )
}