import { NextRequest, NextResponse } from 'next/server'
import { getPortfolio, savePortfolio, PortfolioEntry } from '@/lib/data'
import { getQuotes } from '@/lib/yahoo'
import { randomUUID } from 'crypto'

function calcReturn(
  currentPrice: number | null,
  refPrice: number | null,
  shares: number
): { dollar: number | null; percent: number | null } {
  if (currentPrice == null || refPrice == null || refPrice === 0) {
    return { dollar: null, percent: null }
  }
  return {
    dollar: (currentPrice - refPrice) * shares,
    percent: ((currentPrice - refPrice) / refPrice) * 100,
  }
}

// GET — return portfolio entries enriched with current prices and return metrics
export async function GET() {
  const entries = await getPortfolio()
  const tickers = Array.from(new Set(entries.map((e) => e.ticker)))
  const quotes = await getQuotes(tickers)

  const enriched = entries.map((e) => {
    const q = quotes[e.ticker]
    const currentPrice = q?.regularMarketPrice ?? null
    const totalValue = currentPrice != null ? currentPrice * e.shares : null
    const gainLoss = calcReturn(currentPrice, e.buyPrice, e.shares)
    const today = calcReturn(currentPrice, q?.previousClose ?? null, e.shares)
    const wtd = calcReturn(currentPrice, q?.weekStartPrice ?? null, e.shares)
    const mtd = calcReturn(currentPrice, q?.monthStartPrice ?? null, e.shares)
    const ytd = calcReturn(currentPrice, q?.yearStartPrice ?? null, e.shares)

    return {
      ...e,
      companyName: q?.shortName ?? e.companyName,
      currentPrice,
      totalValue,
      gainLossDollar: gainLoss.dollar,
      gainLossPercent: gainLoss.percent,
      todayDollar: today.dollar,
      todayPercent: today.percent,
      wtdDollar: wtd.dollar,
      wtdPercent: wtd.percent,
      mtdDollar: mtd.dollar,
      mtdPercent: mtd.percent,
      ytdDollar: ytd.dollar,
      ytdPercent: ytd.percent,
      previousClose: q?.previousClose ?? null,
      weekStartPrice: q?.weekStartPrice ?? null,
      monthStartPrice: q?.monthStartPrice ?? null,
      yearStartPrice: q?.yearStartPrice ?? null,
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
