# Stock Tracker

A paper trading and watchlist app built with Next.js 14 (App Router), Tailwind CSS, and yahoo-finance2 for live prices.

## Features

- **Portfolio**: Track paper trades — shares, buy price, current value, gain/loss
- **Watchlist**: Monitor stocks and see price change since you added them
- **Live prices**: Powered by Yahoo Finance via the `yahoo-finance2` package
- **Refresh Prices**: Re-fetch all current prices on demand
- Dark theme, responsive design

## Getting started locally

### Prerequisites

- Node.js 18+

### Install

```bash
cd stock-tracker
npm install
```

### Run dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Data storage

The app uses **Vercel KV** (Redis) in production and automatically falls back to local JSON files (`data/portfolio.json` and `data/watchlist.json`) in development when KV environment variables are not set.

| Environment | Storage backend |
|---|---|
| Local dev (no `.env.local`) | `data/*.json` files |
| Local dev (with `.env.local`) | Vercel KV |
| Vercel preview / production | Vercel KV |

---

## Setting up Vercel KV

### 1. Create a KV store in the Vercel dashboard

1. Open your project in the [Vercel dashboard](https://vercel.com/dashboard)
2. Go to the **Storage** tab → **Create Database** → **KV**
3. Give it a name (e.g. `stock-tracker-kv`) and click **Create**
4. On the store's page, click **Connect Project** and select this project

Vercel automatically adds the required environment variables to your project's **Production**, **Preview**, and **Development** environments.

### 2. Required environment variables

These are injected automatically after connecting the store. You can view them under **Project Settings → Environment Variables**:

| Variable | Description |
|---|---|
| `KV_REST_API_URL` | REST endpoint for the KV store |
| `KV_REST_API_TOKEN` | Read/write token |
| `KV_REST_API_READ_ONLY_TOKEN` | Read-only token (used by `@vercel/kv` internally) |
| `KV_URL` | Full Redis connection URL (not used directly by this app) |

### 3. Pull variables for local development with KV

If you want local dev to read/write the same KV store as production:

```bash
# Install Vercel CLI if you haven't already
npm i -g vercel

# Link the project and pull env vars into .env.local
vercel link
vercel env pull .env.local
```

`.env.local` is gitignored by default. Once it exists, `npm run dev` will use Vercel KV instead of the JSON files.

> **Tip:** Keep a separate KV store for development to avoid polluting production data. You can create a second store in the dashboard and use `vercel env pull --environment=development`.

### 4. Local development without KV (JSON fallback)

No setup required — just run `npm run dev` without a `.env.local` file. Data is stored in `data/portfolio.json` and `data/watchlist.json`, which are created automatically on first write. This is the fastest way to test UI changes locally.

---

## Deploying to Vercel

### Option A — Vercel CLI

```bash
# Preview deployment
vercel

# Production deployment
vercel --prod
```

### Option B — Git integration (recommended)

1. Push this repo to GitHub
2. Go to [vercel.com/new](https://vercel.com/new) and import the repository
3. Vercel detects Next.js automatically — no build configuration needed
4. Every push to `main` deploys to production; every other branch gets a preview URL

Make sure the KV store is connected to the project before deploying so the environment variables are available at runtime.
