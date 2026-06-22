import { useEffect, useState } from 'react'
import { getReportChartBlob } from '../api/client'

interface Props {
  reportId: number
  chartId: string
  title: string
  className?: string
}

export default function ReportChartImage({ reportId, chartId, title, className }: Props) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    setFailed(false)
    setSrc(null)

    getReportChartBlob(reportId, chartId)
      .then((blob) => {
        if (!blob || blob.size < 1024) {
          setFailed(true)
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch(() => setFailed(true))

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [reportId, chartId])

  if (failed) {
    return <div className="py-6 text-center text-xs text-white/40">图表暂不可用（请确认已导入价格数据）</div>
  }
  if (!src) {
    return <div className="py-6 text-center text-xs text-white/40">图表加载中…</div>
  }

  return <img src={src} alt={title} className={className} />
}
