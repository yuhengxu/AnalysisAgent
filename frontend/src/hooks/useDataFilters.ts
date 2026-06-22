import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getDataCatalog } from '../api/client'
import {
  DEFAULT_DATA_QUERY,
  FILTER_STORAGE_KEY,
  type DataCatalog,
  type DataQueryParams,
} from '../types/dataQuery'

function parseList(value: string | null): string[] {
  if (!value) return []
  return value.split(',').map((s) => s.trim()).filter(Boolean)
}

function parseNumber(value: string | null): number | undefined {
  if (!value) return undefined
  const n = Number(value)
  return Number.isFinite(n) ? n : undefined
}

export function paramsFromSearchParams(searchParams: URLSearchParams): DataQueryParams {
  const category = (searchParams.get('category') as DataQueryParams['category']) || DEFAULT_DATA_QUERY.category
  return {
    ...DEFAULT_DATA_QUERY,
    category,
    start_date: searchParams.get('start_date') || undefined,
    end_date: searchParams.get('end_date') || undefined,
    year: parseNumber(searchParams.get('year')),
    month: parseNumber(searchParams.get('month')),
    symbols: parseList(searchParams.get('symbols')) || DEFAULT_DATA_QUERY.symbols,
    agencies: parseList(searchParams.get('agencies')),
    supply_demand: parseList(searchParams.get('supply_demand')),
    periods: parseList(searchParams.get('periods')),
    factor_categories: parseList(searchParams.get('factor_categories')),
    factor_names: parseList(searchParams.get('factor_names')),
  }
}

export function paramsToSearchParams(params: DataQueryParams): URLSearchParams {
  const sp = new URLSearchParams()
  sp.set('category', params.category)
  if (params.start_date) sp.set('start_date', params.start_date)
  if (params.end_date) sp.set('end_date', params.end_date)
  if (params.year) sp.set('year', String(params.year))
  if (params.month) sp.set('month', String(params.month))
  if (params.symbols.length) sp.set('symbols', params.symbols.join(','))
  if (params.agencies.length) sp.set('agencies', params.agencies.join(','))
  if (params.supply_demand.length) sp.set('supply_demand', params.supply_demand.join(','))
  if (params.periods.length) sp.set('periods', params.periods.join(','))
  if (params.factor_categories.length) sp.set('factor_categories', params.factor_categories.join(','))
  if (params.factor_names.length) sp.set('factor_names', params.factor_names.join(','))
  return sp
}

export function useDataFilters(initial?: Partial<DataQueryParams>) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [catalog, setCatalog] = useState<DataCatalog | null>(null)
  const [params, setParams] = useState<DataQueryParams>(() => {
    const fromUrl = paramsFromSearchParams(searchParams)
    if (searchParams.toString()) return { ...fromUrl, ...initial }
    try {
      const saved = localStorage.getItem(FILTER_STORAGE_KEY)
      if (saved) return { ...DEFAULT_DATA_QUERY, ...JSON.parse(saved), ...initial }
    } catch {
      /* ignore */
    }
    return { ...DEFAULT_DATA_QUERY, ...initial }
  })

  const reloadCatalog = useCallback(async () => {
    try {
      setCatalog(await getDataCatalog())
    } catch {
      setCatalog(null)
    }
  }, [])

  useEffect(() => {
    reloadCatalog().catch(() => null)
  }, [reloadCatalog])

  const syncUrl = useCallback(
    (next: DataQueryParams) => {
      setSearchParams(paramsToSearchParams(next), { replace: true })
      localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(next))
    },
    [setSearchParams],
  )

  const updateParams = useCallback(
    (patch: Partial<DataQueryParams>, sync = true) => {
      setParams((prev) => {
        const next = { ...prev, ...patch }
        if (sync) syncUrl(next)
        return next
      })
    },
    [syncUrl],
  )

  const monthOptions = useMemo(() => {
    if (!catalog) return []
    if (params.category === 'balance') return catalog.balance.snapshot_months
    if (params.category === 'factor') return catalog.factor.report_months
    return catalog.price.months
  }, [catalog, params.category])

  return { params, setParams: updateParams, catalog, monthOptions, syncUrl, reloadCatalog }
}
