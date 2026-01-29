import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PriceAgent - Find the Best Prices',
  description: 'AI-powered price comparison and seller contact tool. Find the best deals and negotiate directly with sellers.',
  icons: {
    icon: '/favicon.svg',
  },
  openGraph: {
    title: 'PriceAgent - Find the Best Prices',
    description: 'AI-powered price comparison. Find deals, contact sellers.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background">{children}</body>
    </html>
  )
}
