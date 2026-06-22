import ReactECharts from 'echarts-for-react'

interface SeriesItem {
  name: string
  data: Array<[string | number, number]>
  yAxisIndex?: number
  lineStyle?: { type?: string; width?: number }
}

interface Props {
  config: {
    title?: string
    xAxis?: string
    yAxis?: string
    yAxisRight?: string
    yAxisMin?: number
    yAxisMax?: number
    yAxisRightMin?: number
    yAxisRightMax?: number
    y_axis_scale?: boolean
    dual_y?: boolean
    source?: string
    meta?: {
      start_date?: string
      end_date?: string
      data_source?: string
    }
    series?: SeriesItem[]
  }
  height?: number
}

const axisStyle = {
  axisLabel: { color: '#94a3b8' },
  axisLine: { lineStyle: { color: '#475569' } },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
  nameTextStyle: { color: '#94a3b8' },
}

function buildValueAxis(
  name: string | undefined,
  opts: {
    position?: 'left' | 'right'
    min?: number
    max?: number
    scale?: boolean
    splitLine?: boolean
  } = {},
) {
  return {
    type: 'value' as const,
    name,
    position: opts.position,
    scale: opts.scale ?? false,
    min: opts.min,
    max: opts.max,
    ...axisStyle,
    ...(opts.splitLine === false ? { splitLine: { show: false } } : {}),
  }
}

export default function ChartPanel({ config, height = 320 }: Props) {
  const dualY = !!config.dual_y
  const scaleAxis = !!config.y_axis_scale

  const yAxis = dualY
    ? [
        buildValueAxis(config.yAxis, {
          position: 'left',
          min: config.yAxisMin,
          max: config.yAxisMax,
          scale: scaleAxis,
        }),
        buildValueAxis(config.yAxisRight || '供需差（百万桶/天）', {
          position: 'right',
          min: config.yAxisRightMin,
          max: config.yAxisRightMax,
          scale: scaleAxis,
          splitLine: false,
        }),
      ]
    : buildValueAxis(config.yAxis, {
        min: config.yAxisMin,
        max: config.yAxisMax,
        scale: scaleAxis,
      })

  const option = {
    backgroundColor: 'transparent',
    title: {
      text: config.title,
      textStyle: { color: '#e8eef7', fontSize: 14 },
    },
    tooltip: { trigger: 'axis' },
    legend: {
      textStyle: { color: '#cbd5e1' },
      data: config.series?.map((s) => s.name) || [],
      ...(dualY ? { bottom: 0 } : {}),
    },
    grid: { left: 56, right: dualY ? 64 : 24, top: 48, bottom: dualY ? 64 : 48 },
    xAxis: {
      type: 'category',
      name: config.xAxis,
      axisLabel: { color: '#94a3b8' },
      axisLine: { lineStyle: { color: '#475569' } },
    },
    yAxis,
    series:
      config.series?.map((s) => ({
        name: s.name,
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: s.yAxisIndex ?? 0,
        lineStyle: s.lineStyle,
        data: s.data,
      })) || [],
  }

  return (
    <div className="glass rounded-2xl p-4">
      <ReactECharts option={option} style={{ height }} />
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-white/50">
        {config.source && <span>数据来源：{config.source}</span>}
        {config.meta?.start_date && config.meta?.end_date && (
          <span>
            范围：{config.meta.start_date} ~ {config.meta.end_date}
          </span>
        )}
      </div>
    </div>
  )
}
