import Link from 'next/link'

interface PortfolioRow {
  id: string
  ticker: string
  totalValue: number | null
  gainLossDollar: number | null
}

interface WatchlistRow {
  id: string
}

async function getPortfolio(): Promise<PortfolioRow[]> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL ?? 'http://localhost:3000'}/api/portfolio`, {
      cache: 'no-store',
    })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

async function getWatchlist(): Promise<WatchlistRow[]> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL ?? 'http://localhost:3000'}/api/watchlist`, {
      cache: 'no-store',
    })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

function fmt(n: number | null, prefix = '$') {
  if (n == null) return '—'
  return `${prefix}${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default async function HomePage() {
  const [portfolio, watchlist] = await Promise.all([getPortfolio(), getWatchlist()])

  const totalValue = portfolio.reduce((s, r) => s + (r.totalValue ?? 0), 0)
  const totalGain = portfolio.reduce((s, r) => s + (r.gainLossDollar ?? 0), 0)
  const gainPositive = totalGain >= 0

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white mb-1">Dashboard</h1>
        <p className="text-gray-400 text-sm">Your paper trading overview</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Portfolio Value"
          value={fmt(totalValue)}
          sub={null}
        />
        <StatCard
          label="Total Return"
          value={`${gainPositive ? '+' : '-'}${fmt(totalGain)}`}
          sub={null}
          valueClass={gainPositive ? 'text-green-400' : 'text-red-400'}
        />
        <StatCard
          label="Watching"
          value={String(watchlist.length)}
          sub={`${portfolio.length} positions`}
        />
      </div>

      <div className="flex gap-4">
        <Link
          href="/portfolio"
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
        >
          View Portfolio
        </Link>
        <Link
          href="/watchlist"
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors"
        >
          View Watchlist
        </Link>
        <Link
          href="/add"
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm font-medium transition-colors"
        >
          + Add Stock
        </Link>
      </div>
    </div>
  )
}

function StatCard({
  label,
  value,
  sub,
  valueClass = 'text-white',
}: {
  label: string
  value: string
  sub: string | null
  valueClass?: string
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <p className="text-gray-400 text-xs uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="text-gray-500 text-sm mt-1">{sub}</p>}
    </div>
  )
}
