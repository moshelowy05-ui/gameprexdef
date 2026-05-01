import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Palantir-style dark palette
        surface: {
          50:  "#f0f2f4",
          100: "#d6dce4",
          200: "#b0bcc8",
          300: "#8a9aac",
          400: "#647890",
          500: "#4a5a6a",
          600: "#354554",
          700: "#21303e",
          800: "#141f2b",
          900: "#0a1118",
          950: "#050a0f",
        },
        accent: {
          blue:    "#2d7dd2",
          cyan:    "#14b8d4",
          green:   "#22c55e",
          amber:   "#f59e0b",
          red:     "#ef4444",
          orange:  "#f97316",
          violet:  "#8b5cf6",
        },
        status: {
          active:      "#22c55e",
          caution:     "#f59e0b",
          critical:    "#ef4444",
          offline:     "#6b7280",
          unknown:     "#8b5cf6",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan": "scan 2s linear infinite",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
