'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'

interface Row {
  id: string
  ticker: string
  companyName: string
  priceWhenAdded: number
  dateAdded: string
  currentPrice: number | null
  changeDollar: number | null
  changePercent: number | null
}

function fmt(n: number | null, decimals = 2) {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function GainCell({ value, suffix = '' }: { value: number | null; suffix?: string }) {
  if (value == null) return <span className="text-gray-500">—</span>
  const pos = value >= 0
  return (
    <span className={pos ? 'text-green-400' : 'text-red-400'}>
      {pos ? '+' : '-'}
      {suffix === '%' ? fmt(Math.abs(value)) + '%' : '$' + fmt(Math.abs(value))}
    </span>
  )
}

export default function WatchlistPage() {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    const res = await fetch('/api/watchlist')
    const data = await res.json()
    setRows(data)
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => { load() }, [load])

  const refresh = () => { setRefreshing(true); load() }

  const del = async (id: string) => {
    await fetch(`/api/watchlist?id=${id}`, { method: 'DELETE' })
    setRows((prev) => prev.filter((r) => r.id !== id))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlist</h1>
          <p className="text-gray-400 text-sm mt-0.5">Stocks you are tracking</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
          >
            {refreshing ? 'Refreshing…' : 'Refresh Prices'}
          </button>
          <Link
            href="/add"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
          >
            + Add Stock
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 py-12 text-center">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <p className="text-gray-400 mb-4">No stocks on your watchlist yet.</p>
          <Link href="/add" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium">
            Add your first stock
          </Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="text-left px-4 py-3">Ticker</th>
                  <th className="text-left px-4 py-3">Company</th>
                  <th className="text-right px-4 py-3">Price Added</th>
                  <th className="text-right px-4 py-3">Date Added</th>
                  <th className="text-right px-4 py-3">Current Price</th>
                  <th className="text-right px-4 py-3">Change $</th>
                  <th className="text-right px-4 py-3">Change %</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-blue-400">{r.ticker}</td>
                    <td className="px-4 py-3 text-gray-300 max-w-[160px] truncate">{r.companyName}</td>
                    <td className="px-4 py-3 text-right text-gray-200">${fmt(r.priceWhenAdded)}</td>
                    <td className="px-4 py-3 text-right text-gray-400">{r.dateAdded}</td>
                    <td className="px-4 py-3 text-right text-gray-200">{r.currentPrice != null ? `$${fmt(r.currentPrice)}` : '—'}</td>
                    <td className="px-4 py-3 text-right"><GainCell value={r.changeDollar} /></td>
                    <td className="px-4 py-3 text-right"><GainCell value={r.changePercent} suffix="%" /></td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => del(r.id)}
                        className="text-gray-600 hover:text-red-400 transition-colors text-xs px-2 py-1 rounded hover:bg-red-900/20"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
