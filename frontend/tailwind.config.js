/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'dash-bg': '#0f1117',
        'dash-card': '#1a1d27',
        'dash-border': '#2a2d3a',
        'dash-accent': '#3b82f6',
      },
      keyframes: {
        'slide-in-right': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        'alert-pulse': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(239,68,68,0.7)' },
          '50%': { boxShadow: '0 0 0 8px rgba(239,68,68,0)' },
        },
        'alert-flash': {
          '0%': { backgroundColor: 'rgba(234,179,8,0.3)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
      animation: {
        'slide-in-right': 'slide-in-right 0.3s ease-out forwards',
        'alert-pulse': 'alert-pulse 1.5s ease-in-out infinite',
        'alert-flash': 'alert-flash 1.5s ease-out forwards',
      },
    },
  },
  plugins: [],
};
