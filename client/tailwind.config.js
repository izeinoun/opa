/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // primary (hot pink)
        primary: {
          DEFAULT: '#FE017D',
          50:  '#fff0f7',
          100: '#ffe0ef',
          500: '#FE017D',
          600: '#e5006f',
          700: '#cc0062',
        },
        // opa → maps to primary for backwards compat
        opa: {
          50:  '#fff0f7',
          100: '#ffe0ef',
          500: '#FE017D',
          600: '#e5006f',
          700: '#cc0062',
          900: '#1e3a5f',
        },
        navy:   { DEFAULT: '#1e3a5f', light: '#2a4f7c' },
        teal:   { DEFAULT: '#0d9488', 50: '#f0fdfa', 100: '#ccfbf1', 700: '#0f766e' },
        purple: { DEFAULT: '#7c3aed', 50: '#f5f3ff', 100: '#ede9fe', 700: '#6d28d9' },
      },
    },
  },
  plugins: [],
}
