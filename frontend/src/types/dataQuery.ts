export type DataCategory = 'price' | 'balance' | 'factor' | 'mixed'

export type DataQueryParams = {
  category: DataCategory
  start_date?: string
  end_date?: string
  year?: number
  month?: number
  symbols: string[]
  agencies: string[]
  supply_demand: string[]
  periods: string[]
  factor_categories: string[]
  factor_names: string[]
  indicators: string[]
  page: number
  page_size: number
}

export type AnalysisQueryParams = DataQueryParams & {
  question?: string
  include_charts?: boolean
}

export type DataCatalog = {
  price: {
    symbols: string[]
    month_range: { min: string | null; max: string | null }
    months: string[]
    indicators: string[]
  }
  balance: {
    agencies: string[]
    snapshot_months: string[]
    periods: string[]
    supply_demand: string[]
  }
  factor: {
    report_months: string[]
    categories: string[]
    names: string[]
    indicators: string[]
  }
}

export const DEFAULT_DATA_QUERY: DataQueryParams = {
  category: 'price',
  symbols: ['Brent', 'WTI'],
  agencies: [],
  supply_demand: [],
  periods: [],
  factor_categories: [],
  factor_names: [],
  indicators: [],
  page: 1,
  page_size: 50,
}

export const FILTER_STORAGE_KEY = 'dataQueryParams'
