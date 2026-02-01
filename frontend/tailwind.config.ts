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
        // Light theme with soft pastels
        background: '#FAFAFA',
        surface: '#FFFFFF',
        'surface-hover': '#F5F5F5',
        primary: '#818CF8',      // Soft lavender/indigo
        secondary: '#6B7280',    // Gray-500
        success: '#34D399',      // Soft mint
        warning: '#FBBF24',      // Soft amber
        error: '#F87171',        // Soft red
        // Accent colors
        accent: {
          lavender: '#818CF8',
          pink: '#F472B6',
          mint: '#34D399',
          sky: '#60A5FA',
          peach: '#FDBA74',
        },
      },
      boxShadow: {
        'soft': '0 2px 8px rgba(0,0,0,0.08)',
        'card': '0 4px 12px rgba(0,0,0,0.05)',
        'elevated': '0 8px 24px rgba(0,0,0,0.08)',
      },
    },
  },
  plugins: [],
}
export default config
