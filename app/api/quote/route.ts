import { NextRequest, NextResponse } from 'next/server'
import { getQuote } from '@/lib/yahoo'

export async function GET(req: NextRequest) {
  const ticker = req.nextUrl.searchParams.get('ticker')
  if (!ticker) return NextResponse.json({ error: 'ticker required' }, { status: 400 })

  try {
    const quote = await getQuote(ticker.toUpperCase())
    return NextResponse.json(quote)
  } catch {
    return NextResponse.json({ error: 'Ticker not found' }, { status: 404 })
  }
}
