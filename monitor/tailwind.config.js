/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'arxiv': {
          primary: '#00d4ff',
          secondary: '#00ff88',
          warning: '#ffaa00',
          error: '#ff4444',
          dark: '#1a1a2e',
          card: '#16213e',
          'card-dark': '#0f0f23',
        }
      }
    }
  },
  plugins: [],
}