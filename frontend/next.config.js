/** @type {import('next').NextConfig} */
const nextConfig = {
  // Server mode - no static export
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  env: {
    // API URL for backend:
    // - Production: empty string = relative URLs (FastAPI proxies everything)
    // - Development: localhost:8000 (frontend on :3000, backend on :8000)
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000'),
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || (process.env.NODE_ENV === 'production' ? '' : 'ws://localhost:8000'),
  },
  // Prevent Watchpack from scanning directories outside the project
  webpack: (config) => {
    config.watchOptions = {
      ...config.watchOptions,
      ignored: [
        '**/node_modules/**',
        '**/fbsource/**',
        '/Users/yonigo/fbsource/**',
        '**/.git/**',
      ],
    };
    return config;
  },
}

module.exports = nextConfig
