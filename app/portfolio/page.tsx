'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'

interface Row {
  id: string
  ticker: string
  companyName: string
  shares: number
  buyPrice: number
  buyDate: string
  currentPrice: number | null
  totalValue: number | null
  gainLossDollar: number | null
  gainLossPercent: number | null
  todayDollar: number | null
  todayPercent: number | null
  wtdDollar: number | null
  wtdPercent: number | null
  mtdDollar: number | null
  mtdPercent: number | null
  ytdDollar: number | null
  ytdPercent: number | null
  previousClose: number | null
  weekStartPrice: number | null
  monthStartPrice: number | null
  yearStartPrice: number | null
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

function aggregateReturn(
  rows: Row[],
  getDollar: (r: Row) => number | null,
  getRef: (r: Row) => number | null
): { dollar: number | null; percent: number | null } {
  let dollar = 0
  let basis = 0
  let n = 0
  for (const r of rows) {
    const d = getDollar(r)
    const ref = getRef(r)
    if (d != null && ref != null) {
      dollar += d
      basis += ref * r.shares
      n++
    }
  }
  if (n === 0) return { dollar: null, percent: null }
  return { dollar, percent: basis > 0 ? (dollar / basis) * 100 : null }
}

function fmtReturn(ret: { dollar: number | null; percent: number | null }) {
  if (ret.dollar == null) return { main: '—', sub: '' }
  const sign = ret.dollar >= 0 ? '+' : '-'
  const d = `${sign}$${Math.abs(ret.dollar).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const p = ret.percent != null ? ` ${ret.percent >= 0 ? '+' : ''}${ret.percent.toFixed(2)}%` : ''
  return { main: d, sub: p }
}

export default function PortfolioPage() {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    const res = await fetch('/api/portfolio')
    const data = await res.json()
    setRows(data)
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => { load() }, [load])

  const refresh = () => { setRefreshing(true); load() }

  const del = async (id: string) => {
    await fetch(`/api/portfolio?id=${id}`, { method: 'DELETE' })
    setRows((prev) => prev.filter((r) => r.id !== id))
  }

  const totalValue = rows.reduce((s, r) => s + (r.totalValue ?? 0), 0)
  const costBasis = rows.reduce((s, r) => s + r.buyPrice * r.shares, 0)
  const allTimeDollar = rows.reduce((s, r) => s + (r.gainLossDollar ?? 0), 0)
  const allTimePercent = costBasis > 0 ? (allTimeDollar / costBasis) * 100 : null

  const todayRet = aggregateReturn(rows, (r) => r.todayDollar, (r) => r.previousClose)
  const wtdRet = aggregateReturn(rows, (r) => r.wtdDollar, (r) => r.weekStartPrice)
  const mtdRet = aggregateReturn(rows, (r) => r.mtdDollar, (r) => r.monthStartPrice)
  const ytdRet = aggregateReturn(rows, (r) => r.ytdDollar, (r) => r.yearStartPrice)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-serif text-4xl font-bold text-white tracking-tight">Portfolio</h1>
          <p className="text-white/40 text-sm mt-1">Paper trading positions</p>
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

      {/* Summary stats */}
      {rows.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <SummaryCard label="Positions" value={String(rows.length)} />
            <SummaryCard label="Total Value" value={`$${fmt(totalValue)}`} />
            <SummaryCard label="Cost Basis" value={`$${fmt(costBasis)}`} />
            <SummaryCard
              label="All-time Return"
              value={`${allTimeDollar >= 0 ? '+' : '-'}$${fmt(Math.abs(allTimeDollar))}`}
              sub={allTimePercent != null ? `${allTimePercent >= 0 ? '+' : ''}${allTimePercent.toFixed(2)}%` : undefined}
              pos={allTimeDollar >= 0}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <ReturnCard label="Today" ret={todayRet} />
            <ReturnCard label="Week to Date" ret={wtdRet} />
            <ReturnCard label="Month to Date" ret={mtdRet} />
            <ReturnCard label="Year to Date" ret={ytdRet} />
          </div>
        </>
      )}

      {/* Table / empty / loading */}
      {loading ? (
        <div className="text-white/30 py-16 text-center">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="bg-surface border border-white/[0.06] rounded-2xl p-16 text-center">
          <p className="text-white/40 mb-5">No positions yet.</p>
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
                  <th className="text-right px-4 py-3.5">Shares</th>
                  <th className="text-right px-4 py-3.5">Buy</th>
                  <th className="text-right px-4 py-3.5">Current</th>
                  <th className="text-right px-4 py-3.5">Value</th>
                  <th className="text-right px-4 py-3.5">Today %</th>
                  <th className="text-right px-4 py-3.5">WTD %</th>
                  <th className="text-right px-4 py-3.5">MTD %</th>
                  <th className="text-right px-4 py-3.5">YTD %</th>
                  <th className="text-right px-4 py-3.5">All-time $</th>
                  <th className="text-right px-4 py-3.5">All-time %</th>
                  <th className="px-4 py-3.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-5 py-3.5 font-mono font-bold text-gold">{r.ticker}</td>
                    <td className="px-4 py-3.5 text-white/70 max-w-[140px] truncate">{r.companyName}</td>
                    <td className="px-4 py-3.5 text-right text-white/80 font-mono">{fmt(r.shares, 0)}</td>
                    <td className="px-4 py-3.5 text-right text-white/60 font-mono">${fmt(r.buyPrice)}</td>
                    <td className="px-4 py-3.5 text-right text-white font-mono">{r.currentPrice != null ? `$${fmt(r.currentPrice)}` : '—'}</td>
                    <td className="px-4 py-3.5 text-right text-white font-mono font-medium">{r.totalValue != null ? `$${fmt(r.totalValue)}` : '—'}</td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.todayPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.wtdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.mtdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.ytdPercent} suffix="%" /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.gainLossDollar} /></td>
                    <td className="px-4 py-3.5 text-right"><GainCell value={r.gainLossPercent} suffix="%" /></td>
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

function SummaryCard({
  label,
  value,
  sub,
  pos,
}: {
  label: string
  value: string
  sub?: string
  pos?: boolean
}) {
  const valueClass = pos === undefined ? 'text-white' : pos ? 'text-gold' : 'text-loss'
  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-4">
      <p className="text-white/35 text-xs uppercase tracking-widest mb-2">{label}</p>
      <p className={`text-base font-semibold font-mono ${valueClass}`}>{value}</p>
      {sub && <p className={`text-xs font-mono mt-0.5 ${pos ? 'text-gold/60' : 'text-loss/60'}`}>{sub}</p>}
    </div>
  )
}

function ReturnCard({ label, ret }: { label: string; ret: { dollar: number | null; percent: number | null } }) {
  const pos = ret.dollar == null ? null : ret.dollar >= 0
  const mainClass = pos === null ? 'text-white/30' : pos ? 'text-gold' : 'text-loss'
  const subClass = pos === null ? 'text-white/20' : pos ? 'text-gold/60' : 'text-loss/60'

  const dollarStr =
    ret.dollar == null
      ? '—'
      : `${ret.dollar >= 0 ? '+' : '-'}$${Math.abs(ret.dollar).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const pctStr =
    ret.percent == null ? '' : `${ret.percent >= 0 ? '+' : ''}${ret.percent.toFixed(2)}%`

  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-4">
      <p className="text-white/35 text-xs uppercase tracking-widest mb-2">{label}</p>
      <p className={`text-sm font-semibold font-mono ${mainClass}`}>{dollarStr}</p>
      {pctStr && <p className={`text-xs font-mono mt-0.5 ${subClass}`}>{pctStr}</p>}
    </div>
  )
}
