export interface QuoteResult {
  ticker: string
  shortName: string
  regularMarketPrice: number
  regularMarketChangePercent: number
  previousClose: number | null
  weekStartPrice: number | null
  monthStartPrice: number | null
  yearStartPrice: number | null
}

function findLastCloseBefore(
  timestamps: number[],
  closes: (number | null)[],
  cutoffMs: number
): number | null {
  const cutoffSec = cutoffMs / 1000
  let last: number | null = null
  for (let i = 0; i < timestamps.length; i++) {
    if (timestamps[i] < cutoffSec) {
      if (closes[i] != null) last = closes[i]
    } else {
      break
    }
  }
  return last
}

function getReferenceTimestamps() {
  const now = new Date()

  // Start of current week (Monday 00:00 local time)
  const dow = now.getDay() // 0 = Sun, 1 = Mon, ...
  const daysToMon = dow === 0 ? 6 : dow - 1
  const weekStart = new Date(now)
  weekStart.setDate(weekStart.getDate() - daysToMon)
  weekStart.setHours(0, 0, 0, 0)

  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const yearStart = new Date(now.getFullYear(), 0, 1)

  return {
    weekStartMs: weekStart.getTime(),
    monthStartMs: monthStart.getTime(),
    yearStartMs: yearStart.getTime(),
  }
}

async function fetchChart(ticker: string): Promise<QuoteResult> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1y&interval=1d`
  const res = await fetch(url, {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    next: { revalidate: 0 },
  })

  if (!res.ok) throw new Error(`Yahoo Finance returned ${res.status} for ${ticker}`)

  const json = await res.json()
  const result = json?.chart?.result?.[0]
  if (!result) throw new Error(`No data returned for ${ticker}`)

  const meta = result.meta
  const timestamps: number[] = result.timestamp ?? []
  const closes: (number | null)[] = result.indicators?.quote?.[0]?.close ?? []

  const { weekStartMs, monthStartMs, yearStartMs } = getReferenceTimestamps()

  return {
    ticker: (meta.symbol as string) ?? ticker,
    shortName: (meta.longName as string) ?? (meta.shortName as string) ?? ticker,
    regularMarketPrice: (meta.regularMarketPrice as number) ?? 0,
    regularMarketChangePercent: (meta.regularMarketChangePercent as number) ?? 0,
    previousClose: (meta.chartPreviousClose as number) ?? null,
    weekStartPrice: findLastCloseBefore(timestamps, closes, weekStartMs),
    monthStartPrice: findLastCloseBefore(timestamps, closes, monthStartMs),
    yearStartPrice: findLastCloseBefore(timestamps, closes, yearStartMs),
  }
}

export async function getQuote(ticker: string): Promise<QuoteResult> {
  return fetchChart(ticker.toUpperCase())
}

export async function getQuotes(tickers: string[]): Promise<Record<string, QuoteResult>> {
  if (tickers.length === 0) return {}
  const results = await Promise.allSettled(tickers.map((t) => fetchChart(t.toUpperCase())))
  const map: Record<string, QuoteResult> = {}
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      map[tickers[i].toUpperCase()] = r.value
    }
  })
  return map
}
