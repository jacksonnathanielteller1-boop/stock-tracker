export interface QuoteResult {
  ticker: string
  shortName: string
  regularMarketPrice: number
  regularMarketChangePercent: number
}

async function fetchChart(ticker: string): Promise<QuoteResult> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}`
  const res = await fetch(url, {
    headers: {
      // Yahoo requires a browser-like User-Agent or returns 401/403
      'User-Agent': 'Mozilla/5.0',
    },
    next: { revalidate: 0 }, // always fresh — no Next.js cache
  })

  if (!res.ok) throw new Error(`Yahoo Finance returned ${res.status} for ${ticker}`)

  const json = await res.json()
  const meta = json?.chart?.result?.[0]?.meta

  if (!meta) throw new Error(`No data returned for ${ticker}`)

  return {
    ticker: (meta.symbol as string) ?? ticker,
    shortName: (meta.longName as string) ?? (meta.shortName as string) ?? ticker,
    regularMarketPrice: (meta.regularMarketPrice as number) ?? 0,
    regularMarketChangePercent: (meta.regularMarketChangePercent as number) ?? 0,
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
