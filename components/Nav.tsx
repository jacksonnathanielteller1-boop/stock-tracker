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
    <nav className="border-b border-white/[0.06] bg-black">
      <div className="max-w-7xl mx-auto px-6 flex items-center gap-1 h-14">
        <span className="font-serif text-lg font-bold text-gold mr-8 tracking-wide">
          StockTracker
        </span>
        {links.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-all ${
              pathname === href
                ? 'text-gold bg-gold/10'
                : 'text-white/50 hover:text-white hover:bg-white/[0.04]'
            }`}
          >
            {label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
