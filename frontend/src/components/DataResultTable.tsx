type Props = {
  result: any
}

function renderRows(rows: Record<string, unknown>[]) {
  if (!rows.length) return <p className="text-sm text-white/50">无数据</p>
  const keys = Object.keys(rows[0])
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-white/5 text-left text-white/70">
          <tr>
            {keys.map((k) => (
              <th key={k} className="px-3 py-2">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-t border-white/5">
              {keys.map((k) => (
                <td key={k} className="px-3 py-2">
                  {String(row[k] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DataResultTable({ result }: Props) {
  if (!result) return null

  if (result.category === 'price' || result.price) {
    const block = result.price || result
    const stats = block.monthly_stats || []
    const series = block.series || []
    return (
      <div className="space-y-4">
        {stats.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-white/80">月度统计</h3>
            {renderRows(stats)}
          </div>
        )}
        {series.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium text-white/80">日度序列（{series.length} 条）</h3>
            {renderRows(series.slice(0, 100))}
          </div>
        )}
      </div>
    )
  }

  if (result.category === 'balance' || result.balance) {
    const rows = (result.balance || result).rows || []
    return renderRows(rows)
  }

  if (result.category === 'factor' || result.factor) {
    const rows = (result.factor || result).rows || []
    return renderRows(rows)
  }

  if (result.category === 'mixed') {
    return (
      <div className="space-y-6">
        {result.price && (
          <div>
            <h3 className="mb-2 font-medium">价格</h3>
            <DataResultTable result={{ category: 'price', ...result.price }} />
          </div>
        )}
        {result.balance && (
          <div>
            <h3 className="mb-2 font-medium">供需</h3>
            <DataResultTable result={{ category: 'balance', ...result.balance }} />
          </div>
        )}
        {result.factor && (
          <div>
            <h3 className="mb-2 font-medium">因素</h3>
            <DataResultTable result={{ category: 'factor', ...result.factor }} />
          </div>
        )}
      </div>
    )
  }

  return <p className="text-sm text-white/50">无匹配数据</p>
}
