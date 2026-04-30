import { NextRequest, NextResponse } from 'next/server'
import { getPortfolio, savePortfolio, PortfolioEntry } from '@/lib/data'
import { getQuotes } from '@/lib/yahoo'
import { randomUUID } from 'crypto'

// GET — return portfolio entries enriched with current prices
export async function GET() {
  const entries = await getPortfolio()
  const tickers = Array.from(new Set(entries.map((e) => e.ticker)))
  const quotes = await getQuotes(tickers)

  const enriched = entries.map((e) => {
    const q = quotes[e.ticker]
    const currentPrice = q?.regularMarketPrice ?? null
    const totalValue = currentPrice != null ? currentPrice * e.shares : null
    const gainLossDollar = currentPrice != null ? (currentPrice - e.buyPrice) * e.shares : null
    const gainLossPercent =
      currentPrice != null ? ((currentPrice - e.buyPrice) / e.buyPrice) * 100 : null
    return {
      ...e,
      companyName: q?.shortName ?? e.companyName,
      currentPrice,
      totalValue,
      gainLossDollar,
      gainLossPercent,
    }
  })

  return NextResponse.json(enriched)
}

// POST — add a new portfolio entry
export async function POST(req: NextRequest) {
  const body = await req.json()
  const { ticker, companyName, shares, buyPrice, buyDate } = body as Partial<PortfolioEntry>

  if (!ticker || !shares || !buyPrice || !buyDate) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
  }

  const entries = await getPortfolio()
  const newEntry: PortfolioEntry = {
    id: randomUUID(),
    ticker: ticker.toUpperCase(),
    companyName: companyName ?? ticker.toUpperCase(),
    shares: Number(shares),
    buyPrice: Number(buyPrice),
    buyDate,
  }
  entries.push(newEntry)
  await savePortfolio(entries)
  return NextResponse.json(newEntry, { status: 201 })
}

// DELETE — remove by id
export async function DELETE(req: NextRequest) {
  const id = req.nextUrl.searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 })

  let entries = await getPortfolio()
  entries = entries.filter((e) => e.id !== id)
  await savePortfolio(entries)
  return NextResponse.json({ ok: true })
}
