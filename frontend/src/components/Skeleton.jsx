/**
 * 骨架屏组件
 * 用于在加载过程中显示占位内容，提升用户体验
 */

// 基础骨架元素
export function Skeleton({ className = '', ...props }) {
  return (
    <div
      className={`animate-pulse bg-gray-200 rounded ${className}`}
      {...props}
    />
  )
}

// 论文卡片骨架屏
export function PaperCardSkeleton() {
  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      {/* 顶部一行：序号 + 分类标签 */}
      <div className="flex items-center gap-2 mb-3">
        <Skeleton className="w-8 h-6 rounded" />
        <Skeleton className="w-16 h-5 rounded-full" />
        <Skeleton className="w-12 h-5 rounded-full" />
      </div>

      {/* 标题 */}
      <Skeleton className="h-7 w-3/4 mb-3 rounded" />

      {/* 作者 */}
      <div className="mb-2">
        <Skeleton className="h-4 w-48 rounded" />
      </div>

      {/* 机构 */}
      <div className="mb-2">
        <Skeleton className="h-4 w-32 rounded" />
      </div>

      {/* 日期 */}
      <div className="mb-3">
        <Skeleton className="h-4 w-24 rounded" />
      </div>

      {/* 一段话总结 */}
      <div className="border-l-4 border-gray-200 bg-gray-50 pl-4 py-3 mb-4">
        <Skeleton className="h-3 w-16 mb-2 rounded" />
        <Skeleton className="h-4 w-full mb-1 rounded" />
        <Skeleton className="h-4 w-2/3 rounded" />
      </div>

      {/* 按钮 */}
      <Skeleton className="h-10 w-24 rounded-lg" />
    </div>
  )
}

// 论文列表骨架屏
export function PaperListSkeleton({ count = 5 }) {
  return (
    <div className="divide-y divide-gray-200 bg-white rounded-xl overflow-hidden">
      {Array.from({ length: count }).map((_, index) => (
        <PaperCardSkeleton key={index} />
      ))}
    </div>
  )
}

// 论文详情骨架屏
export function PaperDetailSkeleton() {
  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* 返回链接 */}
        <Skeleton className="h-4 w-16 rounded" />

        {/* 卡片1：基础信息 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          {/* 标题 */}
          <Skeleton className="h-8 w-3/4 mb-4 rounded" />

          {/* 信息行 */}
          <div className="space-y-2">
            <Skeleton className="h-4 w-64 rounded" />
            <Skeleton className="h-4 w-48 rounded" />
            <Skeleton className="h-4 w-32 rounded" />
            <div className="flex gap-2">
              <Skeleton className="h-6 w-16 rounded-full" />
              <Skeleton className="h-6 w-16 rounded-full" />
            </div>
          </div>

          {/* 按钮 */}
          <div className="mt-6 space-y-3">
            <Skeleton className="h-12 w-full rounded-lg" />
            <Skeleton className="h-12 w-full rounded-lg" />
          </div>
        </div>

        {/* 卡片2：一段话总结 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <Skeleton className="h-6 w-24 mb-4 rounded" />
          <Skeleton className="h-4 w-full mb-2 rounded" />
          <Skeleton className="h-4 w-full mb-2 rounded" />
          <Skeleton className="h-4 w-2/3 rounded" />
        </div>

        {/* 卡片3：思维导图 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <Skeleton className="h-6 w-20 mb-4 rounded" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>

        {/* 卡片4：深度分析 */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <Skeleton className="h-6 w-20 mb-4 rounded" />
          <Skeleton className="h-12 w-full rounded-lg" />
        </div>
      </div>
    </div>
  )
}

// 统计数字骨架屏
export function StatsSkeleton() {
  return (
    <div className="bg-white rounded-xl p-6 min-w-[200px]">
      <div className="grid grid-cols-2 gap-6">
        <div>
          <Skeleton className="h-4 w-20 mb-1 rounded" />
          <Skeleton className="h-10 w-16 mb-1 rounded" />
          <Skeleton className="h-3 w-8 rounded" />
        </div>
        <div>
          <Skeleton className="h-4 w-20 mb-1 rounded" />
          <Skeleton className="h-10 w-12 mb-1 rounded" />
          <Skeleton className="h-3 w-8 rounded" />
        </div>
      </div>
    </div>
  )
}