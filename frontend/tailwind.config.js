/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F7F8FA',
        surface: '#FFFFFF',
        ink: '#14181F',
        graphite: '#5A6472',
        hairline: '#E2E6EC',
        accent: '#14545A',
        'accent-soft': '#1E6B72',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
        serif: ['"IBM Plex Serif"', 'Georgia', 'serif'],
      },
      borderRadius: { DEFAULT: '4px', sm: '3px', md: '5px' },
    },
  },
  plugins: [],
};
