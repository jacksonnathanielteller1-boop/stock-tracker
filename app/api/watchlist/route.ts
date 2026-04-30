import { NextRequest, NextResponse } from 'next/server'
import { getWatchlist, saveWatchlist, WatchlistEntry } from '@/lib/data'
import { getQuotes } from '@/lib/yahoo'
import { randomUUID } from 'crypto'

// GET — return watchlist entries enriched with current prices
export async function GET() {
  const entries = await getWatchlist()
  const tickers = [...new Set(entries.map((e) => e.ticker))]
  const quotes = await getQuotes(tickers)

  const enriched = entries.map((e) => {
    const q = quotes[e.ticker]
    const currentPrice = q?.regularMarketPrice ?? null
    const changeDollar = currentPrice != null ? currentPrice - e.priceWhenAdded : null
    const changePercent =
      currentPrice != null ? ((currentPrice - e.priceWhenAdded) / e.priceWhenAdded) * 100 : null
    return {
      ...e,
      companyName: q?.shortName ?? e.companyName,
      currentPrice,
      changeDollar,
      changePercent,
    }
  })

  return NextResponse.json(enriched)
}

// POST — add a new watchlist entry
export async function POST(req: NextRequest) {
  const body = await req.json()
  const { ticker, companyName, priceWhenAdded } = body as Partial<WatchlistEntry>

  if (!ticker || priceWhenAdded == null) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
  }

  const entries = await getWatchlist()
  const newEntry: WatchlistEntry = {
    id: randomUUID(),
    ticker: ticker.toUpperCase(),
    companyName: companyName ?? ticker.toUpperCase(),
    priceWhenAdded: Number(priceWhenAdded),
    dateAdded: new Date().toISOString().split('T')[0],
  }
  entries.push(newEntry)
  await saveWatchlist(entries)
  return NextResponse.json(newEntry, { status: 201 })
}

// DELETE — remove by id
export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 })

  let entries = await getWatchlist()
  entries = entries.filter((e) => e.id !== id)
  await saveWatchlist(entries)
  return NextResponse.json({ ok: true })
}
