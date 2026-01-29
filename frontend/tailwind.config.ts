import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Match existing dashboard dark theme
        background: '#0f172a',
        surface: '#1e293b',
        'surface-hover': '#334155',
        primary: '#60a5fa',
        secondary: '#94a3b8',
        success: '#4ade80',
        warning: '#fbbf24',
        error: '#f87171',
      },
    },
  },
  plugins: [],
}
export default config
