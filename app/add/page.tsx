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
    <div className="max-w-lg space-y-8">
      <div>
        <h1 className="font-serif text-4xl font-bold text-white tracking-tight">Add Stock</h1>
        <p className="text-white/40 text-sm mt-1">Add to your portfolio or watchlist</p>
      </div>

      <form onSubmit={handleSubmit} className="bg-surface border border-white/[0.06] rounded-2xl p-7 space-y-6">
        {/* Type toggle */}
        <div>
          <label className="block text-xs text-white/35 uppercase tracking-widest mb-3">Type</label>
          <div className="flex rounded-lg overflow-hidden border border-white/[0.08]">
            {(['portfolio', 'watchlist'] as Type[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setType(t)}
                className={`flex-1 py-2.5 text-sm font-medium capitalize transition-all ${
                  type === t
                    ? 'bg-gold text-black font-semibold'
                    : 'bg-surface-2 text-white/50 hover:text-white'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Ticker */}
        <div>
          <label className="block text-xs text-white/35 uppercase tracking-widest mb-3">
            Ticker Symbol
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onBlur={() => lookupTicker(ticker)}
              placeholder="e.g. AAPL"
              className="flex-1 bg-black border border-white/[0.08] rounded-lg px-4 py-2.5 text-white placeholder-white/20 focus:outline-none focus:border-gold/40 font-mono uppercase transition-colors"
            />
            <button
              type="button"
              onClick={() => lookupTicker(ticker)}
              disabled={loadingQuote || !ticker}
              className="px-4 py-2.5 border border-white/[0.08] text-white/60 hover:text-white hover:border-gold/30 disabled:opacity-40 rounded-lg text-sm transition-all"
            >
              {loadingQuote ? '…' : 'Lookup'}
            </button>
          </div>
          {quoteError && <p className="text-loss text-xs mt-2">{quoteError}</p>}
          {quote && (
            <div className="mt-3 px-4 py-3 bg-black border border-white/[0.06] rounded-lg text-sm flex items-center justify-between">
              <div>
                <span className="text-gold font-mono font-bold">{quote.ticker}</span>
                <span className="text-white/60 ml-2 text-xs">{quote.shortName}</span>
              </div>
              <span className="text-white font-mono font-semibold">
                ${quote.regularMarketPrice.toFixed(2)}
              </span>
            </div>
          )}
        </div>

        {/* Portfolio-only fields */}
        {type === 'portfolio' && (
          <>
            <div>
              <label className="block text-xs text-white/35 uppercase tracking-widest mb-3">Shares</label>
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="10"
                min="0"
                step="any"
                className="w-full bg-black border border-white/[0.08] rounded-lg px-4 py-2.5 text-white placeholder-white/20 focus:outline-none focus:border-gold/40 font-mono transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-white/35 uppercase tracking-widest mb-3">
                Buy Price (per share)
              </label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30 font-mono">$</span>
                <input
                  type="number"
                  value={buyPrice}
                  onChange={(e) => setBuyPrice(e.target.value)}
                  placeholder="0.00"
                  min="0"
                  step="any"
                  className="w-full bg-black border border-white/[0.08] rounded-lg pl-8 pr-4 py-2.5 text-white placeholder-white/20 focus:outline-none focus:border-gold/40 font-mono transition-colors"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-white/35 uppercase tracking-widest mb-3">Buy Date</label>
              <input
                type="date"
                value={buyDate}
                onChange={(e) => setBuyDate(e.target.value)}
                className="w-full bg-black border border-white/[0.08] rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-gold/40 font-mono transition-colors"
              />
            </div>
          </>
        )}

        {type === 'watchlist' && quote && (
          <p className="text-sm text-white/40">
            Will track from current price of{' '}
            <span className="text-gold font-mono font-semibold">${quote.regularMarketPrice.toFixed(2)}</span>
          </p>
        )}

        {error && <p className="text-loss text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !quote}
          className="w-full py-3 bg-gold text-black rounded-lg font-semibold text-sm hover:bg-gold-dim disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Adding…' : type === 'portfolio' ? 'Add to Portfolio' : 'Add to Watchlist'}
        </button>
      </form>
    </div>
  )
}
