export const BEIJING_TZ = 'Asia/Shanghai'

/** 将 API 时间字符串格式化为北京时间展示。 */
export function formatBeijingTime(iso: string | number | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    timeZone: BEIJING_TZ,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

/** 获取当前北京时间的年月日。 */
export function beijingDateParts(now = new Date()): {
  year: number
  month: number
  day: number
} {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BEIJING_TZ,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).formatToParts(now)
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0)
  return { year: get('year'), month: get('month'), day: get('day') }
}
