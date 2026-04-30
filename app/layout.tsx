import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Nav from '@/components/Nav'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Stock Tracker',
  description: 'Paper trading and watchlist app',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen`}>
        <Nav />
        <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  )
}
