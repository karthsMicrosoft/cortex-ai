/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        indigo: {
          600: '#4F46E5',
        },
      },
      backgroundColor: {
        'dark-base': '#0F172A',
      },
    },
  },
  plugins: [],
};
