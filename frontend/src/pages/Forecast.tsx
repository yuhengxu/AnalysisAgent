import { useEffect, useState } from 'react'
import { getBacktest, listForecasts, runForecast } from '../api/client'

export default function ForecastPage() {
  const [forecasts, setForecasts] = useState<any[]>([])
  const [backtest, setBacktest] = useState<any>(null)
  const [latest, setLatest] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  async function refresh() {
    const [f, b] = await Promise.all([listForecasts(), getBacktest()])
    setForecasts(f)
    setBacktest(b)
  }

  useEffect(() => {
    refresh().catch(() => null)
  }, [])

  async function handleRun() {
    setLoading(true)
    try {
      const result = await runForecast('Brent')
      setLatest(result)
      await refresh()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">预测模型</h1>
        <p className="text-sm text-white/60">基准/乐观/悲观情景预测与简单回测</p>
      </div>

      <div className="glass rounded-2xl p-5">
        <button
          onClick={handleRun}
          disabled={loading}
          className="rounded-xl bg-brand-blue px-4 py-2 text-sm disabled:opacity-50"
        >
          {loading ? '预测中...' : '运行 Brent 预测模型'}
        </button>
        {latest && (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {latest.scenarios?.map((s: any) => (
              <div key={s.scenario} className="rounded-xl bg-white/5 p-4">
                <div className="text-sm capitalize text-white/60">{s.scenario}</div>
                <div className="mt-1 text-xl font-semibold">{s.point} USD/bbl</div>
                <div className="text-xs text-white/50">
                  区间 {s.low} - {s.high}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {backtest && (
        <div className="glass rounded-2xl p-5">
          <h2 className="mb-2 font-medium">回测摘要</h2>
          <div className="text-sm text-white/80">
            MAPE: {backtest.mape ?? '--'}% · 方向准确率: {backtest.direction_accuracy ?? '--'}
          </div>
        </div>
      )}

      <div className="glass overflow-hidden rounded-2xl">
        <table className="min-w-full text-sm">
          <thead className="bg-white/5 text-left">
            <tr>
              <th className="px-4 py-3">周期</th>
              <th className="px-4 py-3">情景</th>
              <th className="px-4 py-3">预测值</th>
              <th className="px-4 py-3">区间</th>
              <th className="px-4 py-3">模型</th>
            </tr>
          </thead>
          <tbody>
            {forecasts.map((f) => (
              <tr key={f.id} className="border-t border-white/5">
                <td className="px-4 py-3">{f.period}</td>
                <td className="px-4 py-3">{f.scenario}</td>
                <td className="px-4 py-3">{f.point_value}</td>
                <td className="px-4 py-3">
                  {f.low_value} - {f.high_value}
                </td>
                <td className="px-4 py-3">{f.model_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
