'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const links = [
  { href: '/', label: 'Home' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/watchlist', label: 'Watchlist' },
  { href: '/add', label: 'Add Stock' },
]

export default function Nav() {
  const pathname = usePathname()
  return (
    <nav className="border-b border-gray-800 bg-gray-900">
      <div className="max-w-6xl mx-auto px-4 flex items-center gap-1 h-14">
        <span className="text-lg font-bold text-white mr-6">
          📈 StockTracker
        </span>
        {links.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              pathname === href
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
