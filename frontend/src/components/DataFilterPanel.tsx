import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { DataCatalog, DataQueryParams } from '../types/dataQuery'

type Props = {
  params: DataQueryParams
  catalog: DataCatalog | null
  monthOptions: string[]
  onChange: (patch: Partial<DataQueryParams>) => void
  showMixed?: boolean
}

const CATEGORIES: { value: DataQueryParams['category']; label: string }[] = [
  { value: 'price', label: '价格' },
  { value: 'balance', label: '供需' },
  { value: 'factor', label: '因素' },
]

function toggleItem(list: string[], item: string): string[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item]
}

function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
  placeholder = '全部',
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState({ top: 0, left: 0, width: 0 })
  const wrapRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  function updateMenuPosition() {
    const el = triggerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setMenuStyle({
      top: rect.bottom + 4,
      left: rect.left,
      width: rect.width,
    })
  }

  useEffect(() => {
    if (!open) return
    updateMenuPosition()
    function handleClick(e: MouseEvent) {
      const target = e.target as Node
      if (wrapRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setOpen(false)
    }
    function handleLayout() {
      updateMenuPosition()
    }
    document.addEventListener('mousedown', handleClick)
    window.addEventListener('resize', handleLayout)
    window.addEventListener('scroll', handleLayout, true)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      window.removeEventListener('resize', handleLayout)
      window.removeEventListener('scroll', handleLayout, true)
    }
  }, [open])

  if (!options.length) return null

  const summary =
    selected.length === 0
      ? placeholder
      : selected.length <= 2
        ? selected.join('、')
        : `已选 ${selected.length} 项`

  const menu =
    open &&
    createPortal(
      <div
        ref={menuRef}
        style={{ top: menuStyle.top, left: menuStyle.left, width: menuStyle.width }}
        className="fixed z-[200] max-h-52 overflow-y-auto rounded-xl border border-white/15 bg-[#151a28] p-2 shadow-2xl"
      >
        <button
          type="button"
          onClick={() => onChange([])}
          className={`mb-1 w-full rounded-lg px-2 py-1.5 text-left text-xs ${
            selected.length === 0 ? 'bg-brand-blue/20 text-brand-blue' : 'text-white/60 hover:bg-white/5'
          }`}
        >
          全部（不筛选）
        </button>
        {options.map((opt) => (
          <label
            key={opt}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-white/5"
            title={opt}
          >
            <input
              type="checkbox"
              checked={selected.includes(opt)}
              onChange={() => onChange(toggleItem(selected, opt))}
              className="h-3.5 w-3.5 shrink-0 rounded accent-brand-red"
            />
            <span className="truncate">{opt}</span>
          </label>
        ))}
      </div>,
      document.body,
    )

  return (
    <div ref={wrapRef} className="relative z-10 min-w-0">
      <span className="mb-1 block text-sm text-white/70">{label}</span>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-left text-sm hover:border-white/20"
      >
        <span className="truncate text-white/90">{summary}</span>
        <span className="shrink-0 text-xs text-white/40">{open ? '▲' : '▼'}</span>
      </button>
      {menu}
    </div>
  )
}

export default function DataFilterPanel({ params, catalog, monthOptions, onChange, showMixed = false }: Props) {
  const categories = showMixed ? [...CATEGORIES, { value: 'mixed' as const, label: '综合' }] : CATEGORIES

  function applyMonth(ym: string) {
    const [y, m] = ym.split('-')
    onChange({ year: Number(y), month: Number(m) })
  }

  const selectedYm =
    params.year && params.month ? `${params.year}-${String(params.month).padStart(2, '0')}` : ''

  const showPrice = params.category === 'price' || params.category === 'mixed'
  const showBalance = params.category === 'balance' || params.category === 'mixed'
  const showFactor = params.category === 'factor' || params.category === 'mixed'

  return (
    <div className="glass space-y-4 rounded-2xl p-5">
      <div className="flex flex-wrap gap-2">
        {categories.map((c) => (
          <button
            key={c.value}
            type="button"
            onClick={() => onChange({ category: c.value })}
            className={`rounded-full px-4 py-1 text-sm ${
              params.category === c.value ? 'bg-brand-blue text-white' : 'bg-white/5 hover:bg-white/10'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {showPrice && (
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-white/70">起始日期</span>
            <input
              type="date"
              value={params.start_date || ''}
              onChange={(e) => onChange({ start_date: e.target.value || undefined })}
              className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-white/70">结束日期</span>
            <input
              type="date"
              value={params.end_date || ''}
              onChange={(e) => onChange({ end_date: e.target.value || undefined })}
              className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2"
            />
          </label>
        </div>
      )}

      {params.category !== 'price' && (
        <label className="block text-sm">
          <span className="mb-1 block text-white/70">年月</span>
          <select
            value={selectedYm}
            onChange={(e) => e.target.value && applyMonth(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2"
          >
            <option value="">选择月份</option>
            {monthOptions.map((ym) => (
              <option key={ym} value={ym}>
                {ym}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {showPrice && (
          <MultiSelectDropdown
            label="品种"
            options={catalog?.price.symbols || ['Brent', 'WTI', 'Dubai', 'Oman']}
            selected={params.symbols}
            onChange={(symbols) => onChange({ symbols })}
          />
        )}
        {showBalance && (
          <>
            <MultiSelectDropdown
              label="机构"
              options={catalog?.balance.agencies || ['IEA', 'EIA', 'S&P']}
              selected={params.agencies}
              onChange={(agencies) => onChange({ agencies })}
            />
            <MultiSelectDropdown
              label="供需类型"
              options={catalog?.balance.supply_demand || ['供', '需', '供需差']}
              selected={params.supply_demand}
              onChange={(supply_demand) => onChange({ supply_demand })}
            />
            <MultiSelectDropdown
              label="周期"
              options={catalog?.balance.periods || []}
              selected={params.periods}
              onChange={(periods) => onChange({ periods })}
            />
          </>
        )}
        {showFactor && (
          <>
            <MultiSelectDropdown
              label="因素大类"
              options={catalog?.factor.categories || []}
              selected={params.factor_categories}
              onChange={(factor_categories) => onChange({ factor_categories })}
            />
            <MultiSelectDropdown
              label="因素名"
              options={catalog?.factor.names || []}
              selected={params.factor_names}
              onChange={(factor_names) => onChange({ factor_names })}
            />
          </>
        )}
      </div>
    </div>
  )
}
