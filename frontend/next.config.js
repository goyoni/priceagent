/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  env: {
    // In production (static export served by FastAPI), use relative URLs
    // In development, use localhost:8000
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || '',
  },
  // Prevent Watchpack from scanning directories outside the project
  webpack: (config) => {
    config.watchOptions = {
      ...config.watchOptions,
      ignored: ['**/node_modules/**', '/Users/yonigo/fbsource/**'],
    };
    return config;
  },
}

module.exports = nextConfig
