/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#2D4351',
          'primary-dark': '#20313C',
          'primary-light': '#3D5B6E',
          'primary-subtle': '#EAEFF2',
          secondary: '#848485',
          'secondary-light': '#EFEFEF',
          'secondary-dark': '#5F5F60',
          bg: '#F8F9FA',
          card: '#FFFFFF',
          border: '#E5E7EB',
          borderSubtle: '#F1F3F5',
        },
        status: {
          new: '#6B7280',
          called: '#3B82F6',
          emailed: '#8B5CF6',
          interested: '#10B981',
          followup: '#F59E0B',
          notinterested: '#EF4444',
          qualified: '#059669',
        }
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
      },
      boxShadow: {
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.04)',
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.06)',
        'dropdown': '0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04)',
        'drawer': '-4px 0 24px rgba(0, 0, 0, 0.08)',
      }
    },
  },
  plugins: [],
}
