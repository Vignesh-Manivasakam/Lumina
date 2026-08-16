/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Modern Research Workspace Palette
        lumina: {
          50: '#F0F6FE',
          100: '#E1EEFE',
          200: '#C8E0FD',
          300: '#A1CBFC',
          400: '#72ADFA',
          500: '#3D8BF7',
          600: '#0A68FF', // Primary brand electric blue
          700: '#0052D6',
          800: '#0042B0',
          900: '#00368C',
          DEFAULT: '#0A68FF',
        },
        workspace: {
          bg: '#F5F9FD',
          surface: '#FFFFFF',
          border: '#DCE5F2',
          borderLight: '#EDF3FA',
          text: '#0F172A',
          muted: '#64748B',
          subtle: '#94A3B8',
          card: '#FFFFFF',
          cardHover: '#FAFCFF',
          darkBg: '#090D16',
          darkSurface: '#111726',
          darkBorder: '#1E293B',
          darkText: '#F1F5F9',
          darkMuted: '#94A3B8',
        },
        // Legacy Archival palette preserved for citations & accent badges
        parchment: {
          DEFAULT: "#F5F0E6",
          50: "#FBF7EE",
          100: "#F5F0E6",
          200: "#EBE3D2",
          300: "#DDD0B7",
        },
        walnut: {
          DEFAULT: "#2A2520",
          50: "#5A4F44",
          100: "#4D4439",
          200: "#3D342B",
          300: "#2A2520",
        },
        oxblood: {
          DEFAULT: "#7C2D26",
          50: "#A04940",
          100: "#8E3830",
          200: "#7C2D26",
          300: "#5E201B",
        },
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
        '3xl': '20px',
        '4xl': '24px',
      },
      boxShadow: {
        'subtle': '0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.02)',
        'card': '0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.02)',
        'card-hover': '0 10px 25px -3px rgba(10, 104, 255, 0.08), 0 4px 10px -2px rgba(15, 23, 42, 0.04)',
        'modal': '0 20px 40px -10px rgba(15, 23, 42, 0.15)',
      },
      animation: {
        'trace-fill': 'traceFill 600ms ease-out forwards',
        'fade-up': 'fadeUp 260ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'pulse-subtle': 'pulseSubtle 3s ease-in-out infinite',
      },
      keyframes: {
        traceFill: {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSubtle: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.85' },
        },
      },
    },
  },
  plugins: [],
};
