/** 月报图表锚点（与 backend sample_contracts.REPORT_CHART_ANCHORS 一致，样例 docx 6 张） */
export const REPORT_CHART_ANCHORS = [
  { id: 'chart_futures_price', section_id: 'review_futures', title: '图1-1  国际原油期货价格走势图' },
  { id: 'chart_brent_position_structure', section_id: 'review_futures', title: '图1-2  ICE Brent原油期货持仓结构走势图' },
  { id: 'chart_brent_position_composition', section_id: 'review_futures', title: '图1-3  ICE Brent原油期货持仓者构成与价格走势图' },
  { id: 'chart_brent_spot_future', section_id: 'review_spot', title: '图1-4  Brent期现货价格走势' },
  { id: 'chart_brent_dubai_spread', section_id: 'review_spot', title: '图1-5  Brent-Dubai现货价差走势' },
  { id: 'chart_brent_espo_spread', section_id: 'review_spot', title: '图1-6  Brent-ESPO价差走势' },
] as const

export function chartsForSection(sectionId: string) {
  return REPORT_CHART_ANCHORS.filter((c) => c.section_id === sectionId)
}

export function reportChartUrl(reportId: number, chartId: string) {
  return `/api/v1/reports/${reportId}/charts/${chartId}`
}

export const DEFAULT_REVISE_INSTRUCTION = '改得更适合领导汇报，保留全部数据与来源'
