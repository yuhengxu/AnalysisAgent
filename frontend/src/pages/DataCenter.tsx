import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { clearData, exportQueryData, fetchReportWebTables, getReportTables, getReportTablesSchema, listDatasets, queryData, saveReportTable, syncReportDerivedTables, uploadFile } from '../api/client'
import { formatDataCenterPeriodNote, getDefaultReviewPeriod, outlookFromReview } from '../constants/agentDefaults'
import { formatBeijingTime } from '../lib/formatTime'
import ChartPanel from '../components/ChartPanel'
import DataFilterPanel from '../components/DataFilterPanel'
import DataResultTable from '../components/DataResultTable'
import { useDataFilters } from '../hooks/useDataFilters'

type ImportResult = {
  import: {
    dataset_id: number
    category: string
    rows?: number
    inserted?: number
    updated?: number
    skipped?: number
    imported_sheets?: string[]
    skipped_sheets?: { sheet: string; reason: string }[]
    message?: string
  }
  quality: {
    passed: boolean
    issues: string[]
  }
  table_sync?: {
    periods: { review_year: number; review_month: number }[]
    synced: Record<string, { synced?: string[]; errors?: Record<string, string> }>
  }
}

type Tab = 'import' | 'browse' | 'quality' | 'reportTables'

type ReportTableEntry = {
  table_key: string
  source_category: string
  exists: boolean
  is_manual_override: boolean
  has_values: boolean
  source_urls: string[]
  table: { title: string; source: string; headers: string[]; rows: string[][] }
}

export default function DataCenter() {
  const [tab, setTab] = useState<Tab>('browse')
  const [datasets, setDatasets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [lastImport, setLastImport] = useState<ImportResult | null>(null)
  const [queryResult, setQueryResult] = useState<any>(null)
  const [exporting, setExporting] = useState(false)
  const { params, setParams, catalog, monthOptions, reloadCatalog } = useDataFilters()
  const defaultReview = getDefaultReviewPeriod()
  const [reviewYear, setReviewYear] = useState(defaultReview.review_year)
  const [reviewMonth, setReviewMonth] = useState(defaultReview.review_month)
  const outlookPeriod = useMemo(
    () => outlookFromReview(reviewYear, reviewMonth),
    [reviewYear, reviewMonth],
  )
  const [pendingImports, setPendingImports] = useState<Record<string, File | null>>({
    price: null,
    balance: null,
    factor: null,
  })
  const [reportTablesData, setReportTablesData] = useState<{
    filled_count: number
    total_count: number
    derived_filled: number
    web_filled: number
    outlook_year?: number
    outlook_month?: number
    tables: ReportTableEntry[]
  } | null>(null)
  const [editableRows, setEditableRows] = useState<Record<string, string[][]>>({})
  const [reportTablesLoading, setReportTablesLoading] = useState(false)
  const [reportTablesSaving, setReportTablesSaving] = useState<string | null>(null)
  const [enableGdpLlmPredict, setEnableGdpLlmPredict] = useState(false)

  async function loadReportTables() {
    setReportTablesLoading(true)
    try {
      const data = await getReportTables(reviewYear, reviewMonth)
      setReportTablesData(data)
      const rowsMap: Record<string, string[][]> = {}
      for (const t of data.tables || []) {
        rowsMap[t.table_key] = (t.table?.rows || []).map((row: string[]) => [...row])
      }
      setEditableRows(rowsMap)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '加载月报表数据失败')
    } finally {
      setReportTablesLoading(false)
    }
  }

  useEffect(() => {
    if (tab !== 'reportTables') return
    loadReportTables().catch(() => null)
    getReportTablesSchema()
      .then((schema) => {
        const def = schema?.web_fetch?.gdp_llm_predict_default
        if (typeof def === 'boolean') setEnableGdpLlmPredict(def)
      })
      .catch(() => null)
  }, [tab, reviewYear, reviewMonth])

  async function handleSyncDerived() {
    setReportTablesLoading(true)
    setMessage('')
    try {
      const result = await syncReportDerivedTables({
        review_year: reviewYear,
        review_month: reviewMonth,
        outlook_year: outlookPeriod.outlook_year,
        outlook_month: outlookPeriod.outlook_month,
      })
      const periodNote = result.periods
        ? `（${result.periods.review_label} → 展望 ${result.periods.outlook_label}）`
        : ''
      setMessage(`派生表已同步${periodNote}：${(result.synced || []).join('、') || '无'}`)
      await loadReportTables()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '同步失败')
    } finally {
      setReportTablesLoading(false)
    }
  }

  async function handleFetchWeb() {
    const periodNote = formatDataCenterPeriodNote(reviewYear, reviewMonth)
    const gdpNote = enableGdpLlmPredict
      ? '含表2-2 大模型预测'
      : '表2-2 手工填写（未勾选大模型预测）'
    if (
      !window.confirm(
        `将按以下期别深度研究联网获取，并写入回顾月 snapshot：\n\n${periodNote}\n${gdpNote}\n\n确认继续？`,
      )
    ) {
      return
    }
    setReportTablesLoading(true)
    setMessage('')
    try {
      const result = await fetchReportWebTables({
        review_year: reviewYear,
        review_month: reviewMonth,
        outlook_year: outlookPeriod.outlook_year,
        outlook_month: outlookPeriod.outlook_month,
        enable_gdp_llm_predict: enableGdpLlmPredict,
      })
      const errText = Object.entries(result.errors || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join('；')
      const skipNotes = Object.entries(result.skip_notes || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join('；')
      const periods = result.periods as
        | { review_label?: string; pmi_label?: string; outlook_label?: string }
        | undefined
      const fetchedNote = periods
        ? `回顾 ${periods.review_label} · PMI ${periods.pmi_label} · 展望 ${periods.outlook_label}`
        : periodNote.replace(/\n/g, ' · ')
      setMessage(
        `深度研究联网：${(result.fetched || []).join('、') || '无'}`
        + `（${fetchedNote}）`
        + `${(result.skipped || []).length ? `；跳过 ${(result.skipped || []).join('、')}` : ''}`
        + `${skipNotes ? `；${skipNotes}` : ''}`
        + `${errText ? `；失败 ${errText}` : ''}`,
      )
      await loadReportTables()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '联网获取失败')
    } finally {
      setReportTablesLoading(false)
    }
  }

  function updateReportCell(tableKey: string, rowIdx: number, colIdx: number, value: string) {
    setEditableRows((prev) => {
      const next = { ...prev }
      const rows = (next[tableKey] || []).map((row) => [...row])
      while (rows.length <= rowIdx) rows.push([])
      while (rows[rowIdx].length <= colIdx) rows[rowIdx].push('')
      rows[rowIdx][colIdx] = value
      next[tableKey] = rows
      return next
    })
  }

  async function handleSaveReportTable(tableKey: string) {
    setReportTablesSaving(tableKey)
    setMessage('')
    try {
      await saveReportTable({
        review_year: reviewYear,
        review_month: reviewMonth,
        table_key: tableKey,
        rows: editableRows[tableKey] || [],
      })
      setMessage(`${tableKey} 已保存`)
      await loadReportTables()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '保存失败')
    } finally {
      setReportTablesSaving(null)
    }
  }

  async function refresh() {
    const data = await listDatasets()
    setDatasets(data)
  }

  useEffect(() => {
    refresh().catch(() => setDatasets([]))
  }, [])

  function handleSelectFile(category: 'price' | 'balance' | 'factor', file: File | undefined) {
    if (!file) return
    setPendingImports((prev) => ({ ...prev, [category]: file }))
    setMessage(`已选择 ${file.name}，请点击「开始导入」`)
  }

  async function handleConfirmImport(category: 'price' | 'balance' | 'factor') {
    const file = pendingImports[category]
    if (!file) {
      setMessage('请先选择文件')
      return
    }
    setLoading(true)
    setMessage('')
    setLastImport(null)
    try {
      const result: ImportResult = await uploadFile(file, category)
      setLastImport(result)
      setPendingImports((prev) => ({ ...prev, [category]: null }))
      await refresh()
      await reloadCatalog()
      const sync = result.table_sync
      const syncNote =
        sync?.periods?.length
          ? `；已同步派生表 ${sync.periods.map((p) => `${p.review_year}年${p.review_month}月`).join('、')}`
          : ''
      const factorMonths = (result.import as { report_months?: string[] }).report_months
      const factorNote = factorMonths?.length ? `；因素月份 ${factorMonths.join('、')}` : ''
      setMessage(`导入成功${syncNote}${factorNote}`)
      if (category === 'factor' && factorMonths?.length) {
        const latest = [...factorMonths].sort()[factorMonths.length - 1]
        const [y, m] = latest.split('-')
        setTab('browse')
        setParams({
          category: 'factor',
          year: Number(y),
          month: Number(m),
        })
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setMessage(typeof detail === 'object' ? detail?.message || JSON.stringify(detail) : detail || '导入失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>, category?: string) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !category) return
    handleSelectFile(category as 'price' | 'balance' | 'factor', file)
  }

  async function handleClear(category?: string) {
    const label = category
      ? { price: '价格', balance: '供需', factor: '预测因素' }[category]
      : '全部'
    if (!window.confirm(`确定清空${label}数据？此操作不可恢复。`)) return
    setLoading(true)
    setMessage('')
    try {
      const result = await clearData(category)
      const total = Object.values(result.counts).reduce((a: number, b: number) => a + b, 0)
      setMessage(`已清空 ${label} 数据，共删除 ${total} 条记录`)
      setLastImport(null)
      setQueryResult(null)
      await refresh()
      await reloadCatalog()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '清空失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleExportExcel() {
    if (!queryResult) return
    setExporting(true)
    try {
      const blob = await exportQueryData(params as unknown as Record<string, unknown>)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const cat = params.category || 'query'
      a.download = `数据中心_${cat}_${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
      setMessage('Excel 已导出')
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  async function handleQuery() {
    setLoading(true)
    try {
      setQueryResult(await queryData(params))
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || '查询失败')
    } finally {
      setLoading(false)
    }
  }

  function renderReportTable(entry: ReportTableEntry) {
    const { table_key, source_category, table, is_manual_override, has_values, source_urls } = entry
    const headers = table.headers || []
    const rows = editableRows[table_key] || table.rows || []
    const readOnly = source_category === 'derived'

    return (
      <div key={table_key} className="rounded-xl border border-white/10 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-4">
            <div>
              <h3 className="font-medium">{table.title || table_key}</h3>
              <p className="text-xs text-white/50">
                {source_category === 'derived' ? '派生（导入/计算）' : '联网（可手工修正）'}
                {has_values ? ' · 已有数据' : ' · 暂无数据'}
                {is_manual_override ? ' · 已手工锁定' : ''}
                {table_key === 'table_agency' && reportTablesData
                  ? ` · 按回顾月存储（对应展望 ${reportTablesData.outlook_year}年${reportTablesData.outlook_month}月）`
                  : ''}
              </p>
            </div>
            {table_key === 'table_demand_forecast' && (
              <label className="flex items-center gap-2 text-xs text-white/70">
                <input
                  type="checkbox"
                  checked={enableGdpLlmPredict}
                  onChange={(e) => setEnableGdpLlmPredict(e.target.checked)}
                  className="rounded border-white/20"
                />
                大模型预测表2-2（默认关，手工填写）
              </label>
            )}
          </div>
          {!readOnly && (
            <button
              type="button"
              onClick={() => handleSaveReportTable(table_key)}
              disabled={reportTablesSaving === table_key}
              className="rounded-lg bg-brand-blue px-4 py-1.5 text-sm disabled:opacity-50"
            >
              {reportTablesSaving === table_key ? '保存中…' : '保存'}
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-white/5 text-left">
              <tr>
                {headers.map((h, i) => (
                  <th key={`${table_key}-h-${i}`} className="px-3 py-2 font-medium text-white/70">
                    {h || '—'}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIdx) => (
                <tr key={`${table_key}-r-${rowIdx}`} className="border-t border-white/5">
                  {headers.map((_, colIdx) => (
                    <td key={`${table_key}-c-${rowIdx}-${colIdx}`} className="px-3 py-1.5">
                      {readOnly || (table_key === 'table_macro_pmi' && colIdx < 2) || colIdx === 0 ? (
                        <span className="text-white/80">{row[colIdx] ?? ''}</span>
                      ) : (
                        <input
                          type="text"
                          value={row[colIdx] ?? ''}
                          onChange={(e) => updateReportCell(table_key, rowIdx, colIdx, e.target.value)}
                          className="w-full min-w-[4rem] rounded border border-white/10 bg-white/5 px-2 py-1"
                        />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {source_urls?.length > 0 && (
          <p className="mt-2 text-xs text-white/40">来源：{source_urls.join('；')}</p>
        )}
        <p className="mt-1 text-xs text-white/40">数据来源：{table.source}</p>
      </div>
    )
  }

  const chart = queryResult?.charts?.[0]
  const tableData = queryResult?.data || queryResult

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">数据中心</h1>
        <p className="text-sm text-white/60">导入、浏览与质量检查 — 筛选器与智能分析页完全一致</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {([
            ['browse', '浏览'],
            ['quality', '质量'],
            ['reportTables', '月报表数据'],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-full px-4 py-1 text-sm ${
                tab === id ? 'bg-brand-blue text-white' : 'bg-white/5 hover:bg-white/10'
              }`}
            >
              {label}
            </button>
          ))}
          <Link
            to={`/analysis?${new URLSearchParams({ category: params.category }).toString()}`}
            className="rounded-full bg-white/5 px-4 py-1 text-sm hover:bg-white/10"
          >
            前往智能分析 →
          </Link>
        </div>
        <button
          type="button"
          onClick={() => setTab('import')}
          className={`rounded-xl px-5 py-2 text-sm font-medium ${
            tab === 'import' ? 'bg-brand-red text-white' : 'bg-white/10 hover:bg-white/15'
          }`}
        >
          导入
        </button>
      </div>

      {tab === 'import' && (
        <div className="space-y-4">
          <div className="glass grid gap-4 rounded-2xl p-5 md:grid-cols-3">
            {([
              ['price', '上传价格数据', '原油价格表.xlsx'],
              ['balance', '上传供需数据', '供需平衡表.xlsx'],
              ['factor', '上传预测因素表', '油价预测分析表.xlsx'],
            ] as const).map(([cat, title, hint]) => (
              <div
                key={cat}
                className={`rounded-xl border border-dashed border-white/20 p-6 text-center ${
                  loading ? 'pointer-events-none opacity-50' : ''
                }`}
              >
                <label className="block cursor-pointer">
                  <div className="font-medium">{title}</div>
                  <div className="mt-1 text-xs text-white/50">{hint}</div>
                  <div className="mt-2 text-xs text-brand-blue">点击选择文件</div>
                  <input
                    type="file"
                    className="hidden"
                    accept=".csv,.xlsx,.xls"
                    disabled={loading}
                    onChange={(e) => handleUpload(e, cat)}
                  />
                </label>
                {pendingImports[cat] && (
                  <p className="mt-3 truncate text-xs text-white/70">待导入：{pendingImports[cat]!.name}</p>
                )}
                <button
                  type="button"
                  disabled={loading || !pendingImports[cat]}
                  onClick={() => handleConfirmImport(cat)}
                  className="mt-3 rounded-lg bg-brand-blue px-4 py-1.5 text-sm disabled:opacity-40"
                >
                  开始导入
                </button>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-3">
            <button onClick={refresh} className="rounded-xl bg-white/10 px-4 py-2 text-sm">
              刷新列表
            </button>
            <button
              onClick={() => handleClear('price')}
              disabled={loading}
              className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm text-red-200 disabled:opacity-50"
            >
              清空价格
            </button>
            <button
              onClick={() => handleClear('balance')}
              disabled={loading}
              className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm text-red-200 disabled:opacity-50"
            >
              清空供需
            </button>
            <button
              onClick={() => handleClear('factor')}
              disabled={loading}
              className="rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm text-red-200 disabled:opacity-50"
            >
              清空因素
            </button>
            <button
              onClick={() => handleClear()}
              disabled={loading}
              className="rounded-xl border border-red-400/40 bg-red-500/20 px-4 py-2 text-sm text-red-100 disabled:opacity-50"
            >
              清空全部
            </button>
          </div>

          {lastImport && (
            <div className="glass space-y-4 rounded-2xl p-5">
              <h2 className="text-lg font-medium">导入结果</h2>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-white/5 p-4 text-sm">
                  <div className="mb-2 font-medium">入库信息</div>
                  <ul className="space-y-1 text-white/70">
                    <li>数据集 ID：{lastImport.import.dataset_id}</li>
                    <li>类别：{lastImport.import.category}</li>
                    <li>行数：{lastImport.import.rows ?? '—'}</li>
                    <li>新增/更新：{lastImport.import.inserted ?? 0} / {lastImport.import.updated ?? 0}</li>
                  </ul>
                  {lastImport.import.imported_sheets && (
                    <p className="mt-2 text-green-300">成功 sheet：{lastImport.import.imported_sheets.length} 个</p>
                  )}
                </div>
                <div className="rounded-xl bg-white/5 p-4 text-sm">
                  <div className="mb-2 font-medium">质量检查</div>
                  <div
                    className={`mb-2 inline-block rounded-full px-3 py-0.5 text-xs ${
                      lastImport.quality.passed ? 'bg-green-500/20 text-green-300' : 'bg-yellow-500/20 text-yellow-300'
                    }`}
                  >
                    {lastImport.quality.passed ? '通过' : '存在问题'}
                  </div>
                  {lastImport.quality.issues.map((issue) => (
                    <p key={issue} className="text-white/70">
                      {issue}
                    </p>
                  ))}
                </div>
              </div>
              {lastImport.import.skipped_sheets && lastImport.import.skipped_sheets.length > 0 && (
                <div className="rounded-xl bg-yellow-500/10 p-4 text-sm text-yellow-200">
                  <div className="mb-2 font-medium">跳过的 sheet</div>
                  <ul className="space-y-1">
                    {lastImport.import.skipped_sheets.map((s) => (
                      <li key={s.sheet}>
                        {s.sheet} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'browse' && (
        <>
          <DataFilterPanel params={params} catalog={catalog} monthOptions={monthOptions} onChange={setParams} />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleQuery}
              disabled={loading}
              className="rounded-xl bg-brand-blue px-5 py-2 text-sm font-medium disabled:opacity-50"
            >
              {loading ? '查询中…' : '查询数据'}
            </button>
            {queryResult && (
              <button
                type="button"
                onClick={handleExportExcel}
                disabled={exporting}
                className="rounded-xl bg-white/10 px-5 py-2 text-sm font-medium disabled:opacity-50"
              >
                {exporting ? '导出中…' : '导出 Excel'}
              </button>
            )}
          </div>
          {queryResult && (
            <div className="space-y-4">
              {queryResult.charts?.length > 0 && (
                <div className="glass space-y-4 rounded-2xl p-5">
                  {queryResult.charts.map((c: any, idx: number) => (
                    <ChartPanel key={idx} config={c} height={280} />
                  ))}
                </div>
              )}
              {chart && !queryResult.charts?.length && (
                <div className="glass rounded-2xl p-5">
                  <ChartPanel config={chart} height={280} />
                </div>
              )}
              <div className="glass rounded-2xl p-5">
                <DataResultTable result={tableData} />
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'quality' && (
        <div className="glass overflow-hidden rounded-2xl">
          <table className="min-w-full text-sm">
            <thead className="bg-white/5 text-left text-white/70">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">名称</th>
                <th className="px-4 py-3">类别</th>
                <th className="px-4 py-3">行数</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={d.id} className="border-t border-white/5">
                  <td className="px-4 py-3">{d.id}</td>
                  <td className="px-4 py-3">{d.name}</td>
                  <td className="px-4 py-3">{d.category}</td>
                  <td className="px-4 py-3">{d.row_count}</td>
                  <td className="px-4 py-3">{d.status}</td>
                  <td className="px-4 py-3">{formatBeijingTime(d.created_at)}</td>
                </tr>
              ))}
              {datasets.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-white/50">
                    暂无数据集
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'reportTables' && (
        <div className="glass space-y-4 rounded-2xl p-5">
          <div>
            <h2 className="text-lg font-medium">月报表数据</h2>
            <p className="mt-1 text-sm text-white/60">
              按回顾月预置 6 张动态表（表1-1、2-3 等取回顾月数据；表3-1 取对应展望月预测）。
              生成 {outlookPeriod.outlook_year}年{outlookPeriod.outlook_month}月 月报时，将加载本回顾月 snapshot。
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="text-white/60">回顾年</span>
              <input
                type="number"
                value={reviewYear}
                onChange={(e) => setReviewYear(Number(e.target.value))}
                className="ml-2 w-24 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5"
              />
            </label>
            <label className="text-sm">
              <span className="text-white/60">回顾月</span>
              <select
                value={reviewMonth}
                onChange={(e) => setReviewMonth(Number(e.target.value))}
                className="ml-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5"
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>{m}月</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleSyncDerived}
              disabled={reportTablesLoading}
              className="rounded-xl bg-brand-blue px-5 py-2 text-sm font-medium disabled:opacity-50"
            >
              同步派生数据
            </button>
            <button
              type="button"
              onClick={handleFetchWeb}
              disabled={reportTablesLoading}
              className="rounded-xl bg-white/10 px-5 py-2 text-sm font-medium disabled:opacity-50"
            >
              深度研究联网获取
            </button>
          </div>
          {reportTablesData && (
            <p className="text-sm text-white/60">
              已填 {reportTablesData.filled_count}/{reportTablesData.total_count}
              （派生 {reportTablesData.derived_filled}/3，联网 {reportTablesData.web_filled}/3）
            </p>
          )}
          {reportTablesLoading && !reportTablesData && (
            <p className="text-sm text-white/50">加载中…</p>
          )}
          <div className="space-y-4">
            {(reportTablesData?.tables || []).map((entry) => renderReportTable(entry))}
          </div>
        </div>
      )}

      {message && <div className="rounded-xl bg-black/30 p-3 text-sm">{message}</div>}
    </div>
  )
}
