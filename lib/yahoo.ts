import yahooFinance from 'yahoo-finance2'

export interface QuoteResult {
  ticker: string
  shortName: string
  regularMarketPrice: number
  regularMarketChangePercent: number
}

export async function getQuote(ticker: string): Promise<QuoteResult> {
  const quote = await yahooFinance.quote(ticker)
  return {
    ticker: quote.symbol,
    shortName: quote.shortName ?? quote.longName ?? ticker,
    regularMarketPrice: quote.regularMarketPrice ?? 0,
    regularMarketChangePercent: quote.regularMarketChangePercent ?? 0,
  }
}

export async function getQuotes(tickers: string[]): Promise<Record<string, QuoteResult>> {
  if (tickers.length === 0) return {}
  const results = await Promise.allSettled(tickers.map((t) => getQuote(t)))
  const map: Record<string, QuoteResult> = {}
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') {
      map[tickers[i]] = r.value
    }
  })
  return map
}
