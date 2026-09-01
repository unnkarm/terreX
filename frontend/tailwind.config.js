/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        void: "#000000",
        surface: "#080808",
        "surface-raised": "#111111",
        "surface-border": "#222222",
        "surface-border-bright": "#333333",
        radar: {
          DEFAULT: "#22c55e",
          muted: "#16a34a",
          dark: "#14532d",
        },
        panel: "#0a0a0a",
        panel2: "#121212",
        accent: "#22c55e",
        warn: "#eab308",
        danger: "#ef4444",
        ok: "#22c55e",
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
