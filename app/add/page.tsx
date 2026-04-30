'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

type Type = 'portfolio' | 'watchlist'

interface QuoteResult {
  ticker: string
  shortName: string
  regularMarketPrice: number
}

export default function AddStockPage() {
  const router = useRouter()
  const [type, setType] = useState<Type>('portfolio')
  const [ticker, setTicker] = useState('')
  const [quote, setQuote] = useState<QuoteResult | null>(null)
  const [quoteError, setQuoteError] = useState('')
  const [loadingQuote, setLoadingQuote] = useState(false)

  const [shares, setShares] = useState('')
  const [buyPrice, setBuyPrice] = useState('')
  const [buyDate, setBuyDate] = useState(new Date().toISOString().split('T')[0])

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const lookupTicker = async (t: string) => {
    if (!t.trim()) return
    setLoadingQuote(true)
    setQuoteError('')
    setQuote(null)
    try {
      const res = await fetch(`/api/quote?ticker=${encodeURIComponent(t.trim())}`)
      if (!res.ok) throw new Error('Not found')
      const data: QuoteResult = await res.json()
      setQuote(data)
      // Pre-fill buy price with current market price
      setBuyPrice(String(data.regularMarketPrice.toFixed(2)))
    } catch {
      setQuoteError('Ticker not found. Check the symbol and try again.')
    } finally {
      setLoadingQuote(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!ticker.trim()) { setError('Enter a ticker symbol.'); return }
    if (!quote) { setError('Look up a valid ticker first.'); return }

    setSubmitting(true)
    try {
      if (type === 'portfolio') {
        if (!shares || !buyPrice || !buyDate) { setError('Fill in all fields.'); setSubmitting(false); return }
        const res = await fetch('/api/portfolio', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker: ticker.trim().toUpperCase(),
            companyName: quote.shortName,
            shares: parseFloat(shares),
            buyPrice: parseFloat(buyPrice),
            buyDate,
          }),
        })
        if (!res.ok) throw new Error('Failed to add')
        router.push('/portfolio')
      } else {
        const res = await fetch('/api/watchlist', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker: ticker.trim().toUpperCase(),
            companyName: quote.shortName,
            priceWhenAdded: quote.regularMarketPrice,
          }),
        })
        if (!res.ok) throw new Error('Failed to add')
        router.push('/watchlist')
      }
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Add Stock</h1>
        <p className="text-gray-400 text-sm mt-0.5">Add to your portfolio or watchlist</p>
      </div>

      <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
        {/* Type toggle */}
        <div>
          <label className="block text-xs text-gray-400 uppercase tracking-wider mb-2">Type</label>
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            {(['portfolio', 'watchlist'] as Type[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setType(t)}
                className={`flex-1 py-2 text-sm font-medium capitalize transition-colors ${
                  type === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Ticker */}
        <div>
          <label className="block text-xs text-gray-400 uppercase tracking-wider mb-2">
            Ticker Symbol
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onBlur={() => lookupTicker(ticker)}
              placeholder="e.g. AAPL"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 font-mono uppercase"
            />
            <button
              type="button"
              onClick={() => lookupTicker(ticker)}
              disabled={loadingQuote || !ticker}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg text-sm transition-colors"
            >
              {loadingQuote ? '…' : 'Lookup'}
            </button>
          </div>
          {quoteError && <p className="text-red-400 text-xs mt-1">{quoteError}</p>}
          {quote && (
            <div className="mt-2 px-3 py-2 bg-gray-800 rounded-lg text-sm">
              <span className="text-blue-400 font-mono font-semibold">{quote.ticker}</span>
              <span className="text-gray-300 ml-2">{quote.shortName}</span>
              <span className="text-white font-semibold ml-auto float-right">
                ${quote.regularMarketPrice.toFixed(2)}
              </span>
            </div>
          )}
        </div>

        {/* Portfolio-only fields */}
        {type === 'portfolio' && (
          <>
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-2">Shares</label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="10"
                min="0"
                step="any"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-2">
                Buy Price (per share)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                <input
                  type="number"
                  value={buyPrice}
                  onChange={(e) => setBuyPrice(e.target.value)}
                  placeholder="0.00"
                  min="0"
                  step="any"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-7 pr-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 uppercase tracking-wider mb-2">Buy Date</label>
              <input
                type="date"
                value={buyDate}
                onChange={(e) => setBuyDate(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </>
        )}

        {type === 'watchlist' && quote && (
          <p className="text-sm text-gray-400">
            Will track from current price of{' '}
            <span className="text-white font-semibold">${quote.regularMarketPrice.toFixed(2)}</span>
          </p>
        )}

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !quote}
          className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
        >
          {submitting ? 'Adding…' : type === 'portfolio' ? 'Add to Portfolio' : 'Add to Watchlist'}
        </button>
      </form>
    </div>
  )
}
