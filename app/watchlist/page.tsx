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
  todayDollar: number | null
  todayPercent: number | null
  wtdPercent: number | null
  mtdPercent: number | null
  ytdPercent: number | null
}

function fmt(n: number | null, decimals = 2) {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function GainCell({ value, suffix = '' }: { value: number | null; suffix?: string }) {
  if (value == null) return <span className="text-white/20">—</span>
  const pos = value >= 0
  const cls = pos ? 'text-gold' : 'text-loss'
  return (
    <span className={`font-mono ${cls}`}>
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
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-serif text-4xl font-bold text-white tracking-tight">Watchlist</h1>
          <p className="text-white/40 text-sm mt-1">Stocks you are tracking</p>
        </div>
        <div className="flex gap-3 mt-1">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="px-4 py-2 border border-white/10 text-white/60 rounded-lg text-sm font-medium hover:border-gold/30 hover:text-white disabled:opacity-40 transition-all"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          <Link
            href="/add"
            className="px-4 py-2 bg-gold text-black rounded-lg text-sm font-semibold hover:bg-gold-dim transition-colors"
          >
            + Add Stock
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="text-white/30 py-16 text-center">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="bg-surface border border-white/[0.06] rounded-2xl p-16 text-center">
          <p className="text-white/40 mb-5">No stocks on your watchlist yet.</p>
          <Link
            href="/add"
            className="px-5 py-2.5 bg-gold text-black rounded-lg text-sm font-semibold hover:bg-gold-dim transition-colors"
          >
            Add your first stock
          </Link>
        </div>
      ) : (
        <div className="bg-surface border border-white/[0.06] rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-white/35 text-xs uppercase tracking-widest">
                  <th className="text-left px-5 py-3.5">Ticker</th>
                  <th className="text-left px-4 py-3.5">Company</th>
                  <th className="text-right px-4 py-3.5">Added At</th>
                  <th className="text-right px-4 py-3.5">Date</th>
                  <th className="text-right px-4 py-3.5">Current</th>
                  <th className="text-right px-4 py-3.5">Today %</th>
                  <th className="text-right px-4 py-3.5">WTD %</th>
                  <th className="text-right px-4 py-3.5">MTD %</th>
                  <th className="text-right px-4 py-3.5">YTD %</th>
                  <th className="text-right px-4 py-3.5">Since Added $</th>
                  <th className="text-right px-4 py-3.5">Since Added %</th>
                  <th className="px-4 py-3.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-5 py-3.5 font-mono font-bold text-gold">{r.ticker}</td>
                    <td className="px-4 py-3.5 text-white/70 max-w-[140px] truncate">{r.companyName}</td>
                    <td className="px-4 py-3.5 text-right text-white/60 font-mono">${fmt(r.priceWhenAdded)}</td>
                    <td className="px-4 py-3.5 text-right text-white/40 font-mono text-xs">{r.dateAdded}</td>
                    <td className="px-4 py-3.5 text-right text-white font-mono">{r.currentPrice != null ? `$${fmt(r.currentPrice)}` : '—'}</td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.todayPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.wtdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.mtdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.ytdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.changeDollar} /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.changePercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={() => del(r.id)}
                        className="text-white/20 hover:text-loss transition-colors text-xs px-2 py-1 rounded hover:bg-loss/10"
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
