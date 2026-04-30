import Link from 'next/link'

interface PortfolioRow {
  id: string
  ticker: string
  shares: number
  buyPrice: number
  totalValue: number | null
  gainLossDollar: number | null
  gainLossPercent: number | null
  todayDollar: number | null
  wtdDollar: number | null
  mtdDollar: number | null
  ytdDollar: number | null
  previousClose: number | null
  weekStartPrice: number | null
  monthStartPrice: number | null
  yearStartPrice: number | null
}

interface WatchlistRow {
  id: string
}

async function getPortfolio(): Promise<PortfolioRow[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_BASE_URL ?? 'http://localhost:3000'}/api/portfolio`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

async function getWatchlist(): Promise<WatchlistRow[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_BASE_URL ?? 'http://localhost:3000'}/api/watchlist`,
      { cache: 'no-store' }
    )
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

function aggregateReturn(
  rows: PortfolioRow[],
  getDollar: (r: PortfolioRow) => number | null,
  getRef: (r: PortfolioRow) => number | null
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

function fmtDollar(n: number | null): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(n: number | null): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

export default async function HomePage() {
  const [portfolio, watchlist] = await Promise.all([getPortfolio(), getWatchlist()])

  const totalValue = portfolio.reduce((s, r) => s + (r.totalValue ?? 0), 0)
  const costBasis = portfolio.reduce((s, r) => s + r.buyPrice * r.shares, 0)
  const allTimeDollar = portfolio.reduce((s, r) => s + (r.gainLossDollar ?? 0), 0)
  const allTimePercent = costBasis > 0 ? (allTimeDollar / costBasis) * 100 : null

  const todayRet = aggregateReturn(portfolio, (r) => r.todayDollar, (r) => r.previousClose)
  const wtdRet = aggregateReturn(portfolio, (r) => r.wtdDollar, (r) => r.weekStartPrice)
  const mtdRet = aggregateReturn(portfolio, (r) => r.mtdDollar, (r) => r.monthStartPrice)
  const ytdRet = aggregateReturn(portfolio, (r) => r.ytdDollar, (r) => r.yearStartPrice)

  return (
    <div className="space-y-10">
      {/* Header */}
      <div>
        <h1 className="font-serif text-4xl font-bold text-white tracking-tight">Dashboard</h1>
        <p className="text-white/40 text-sm mt-1">Your paper trading overview</p>
      </div>

      {/* Primary stat */}
      <div className="bg-surface border border-white/[0.06] rounded-2xl p-8">
        <p className="text-white/40 text-xs uppercase tracking-widest mb-2">Portfolio Value</p>
        <p className="font-serif text-5xl font-bold text-white">
          ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </p>
        <p className="text-white/30 text-sm mt-2">{portfolio.length} position{portfolio.length !== 1 ? 's' : ''}</p>
      </div>

      {/* Return metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <ReturnCard label="Today" ret={todayRet} />
        <ReturnCard label="Week to Date" ret={wtdRet} />
        <ReturnCard label="Month to Date" ret={mtdRet} />
        <ReturnCard label="Year to Date" ret={ytdRet} />
        <ReturnCard
          label="All-time"
          ret={{ dollar: allTimeDollar, percent: allTimePercent }}
        />
      </div>

      {/* Watchlist + links */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="bg-surface border border-white/[0.06] rounded-xl px-5 py-4 flex items-center gap-4">
          <span className="text-white/40 text-xs uppercase tracking-widest">Watching</span>
          <span className="text-white font-semibold text-lg">{watchlist.length}</span>
        </div>
        <div className="flex gap-3">
          <Link
            href="/portfolio"
            className="px-5 py-2.5 bg-gold text-black rounded-lg text-sm font-semibold hover:bg-gold-dim transition-colors"
          >
            View Portfolio
          </Link>
          <Link
            href="/watchlist"
            className="px-5 py-2.5 border border-white/10 text-white/70 rounded-lg text-sm font-medium hover:border-gold/30 hover:text-white transition-colors"
          >
            View Watchlist
          </Link>
          <Link
            href="/add"
            className="px-5 py-2.5 border border-white/10 text-white/70 rounded-lg text-sm font-medium hover:border-gold/30 hover:text-white transition-colors"
          >
            + Add Stock
          </Link>
        </div>
      </div>
    </div>
  )
}

function ReturnCard({
  label,
  ret,
}: {
  label: string
  ret: { dollar: number | null; percent: number | null }
}) {
  const pos = ret.dollar == null ? null : ret.dollar >= 0
  const dollarClass = pos === null ? 'text-white/30' : pos ? 'text-gold' : 'text-loss'
  const pctClass = pos === null ? 'text-white/20' : pos ? 'text-gold/70' : 'text-loss/70'

  return (
    <div className="bg-surface border border-white/[0.06] rounded-xl p-4">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-3">{label}</p>
      <p className={`text-base font-semibold font-mono ${dollarClass}`}>
        {fmtDollar(ret.dollar)}
      </p>
      <p className={`text-xs font-mono mt-0.5 ${pctClass}`}>
        {fmtPct(ret.percent)}
      </p>
    </div>
  )
}
