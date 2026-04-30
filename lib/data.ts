import fs from 'fs'
import path from 'path'

export interface PortfolioEntry {
  id: string
  ticker: string
  companyName: string
  shares: number
  buyPrice: number
  buyDate: string // ISO date string
}

export interface WatchlistEntry {
  id: string
  ticker: string
  companyName: string
  priceWhenAdded: number
  dateAdded: string // ISO date string
}

// ---------------------------------------------------------------------------
// Backend detection
// KV is used when KV_REST_API_URL is present (set automatically by Vercel KV).
// Falls back to local JSON files for development without KV credentials.
// ---------------------------------------------------------------------------

const useKV = !!process.env.KV_REST_API_URL

// ---------------------------------------------------------------------------
// Vercel KV backend
// ---------------------------------------------------------------------------

async function kvGet<T>(key: string): Promise<T[]> {
  const { kv } = await import('@vercel/kv')
  const data = await kv.get<T[]>(key)
  return data ?? []
}

async function kvSet<T>(key: string, data: T[]): Promise<void> {
  const { kv } = await import('@vercel/kv')
  await kv.set(key, data)
}

// ---------------------------------------------------------------------------
// JSON file fallback (local development)
// ---------------------------------------------------------------------------

const dataDir = path.join(process.cwd(), 'data')

function jsonRead<T>(filename: string): T[] {
  const filepath = path.join(dataDir, filename)
  if (!fs.existsSync(filepath)) return []
  return JSON.parse(fs.readFileSync(filepath, 'utf-8')) as T[]
}

function jsonWrite<T>(filename: string, data: T[]): void {
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true })
  fs.writeFileSync(path.join(dataDir, filename), JSON.stringify(data, null, 2))
}

// ---------------------------------------------------------------------------
// Public API — same signatures as before; API routes need no changes
// ---------------------------------------------------------------------------

export async function getPortfolio(): Promise<PortfolioEntry[]> {
  if (useKV) return kvGet<PortfolioEntry>('portfolio')
  return jsonRead<PortfolioEntry>('portfolio.json')
}

export async function savePortfolio(data: PortfolioEntry[]): Promise<void> {
  if (useKV) return kvSet('portfolio', data)
  jsonWrite('portfolio.json', data)
}

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  if (useKV) return kvGet<WatchlistEntry>('watchlist')
  return jsonRead<WatchlistEntry>('watchlist.json')
}

export async function saveWatchlist(data: WatchlistEntry[]): Promise<void> {
  if (useKV) return kvSet('watchlist', data)
  jsonWrite('watchlist.json', data)
}
