/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Laqta identity ramp — the single violet scale every brand surface
           (logo, dashboard, studio accents) draws from. */
        laqta: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c4dff",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
          950: "#2e1065",
        },
        brand: {
          50: "#f5f3ff",
          100: "#ede9fe",
          500: "#8b5cf6",
          600: "#7c4dff",
          700: "#6d28d9",
        },
        obsidian: {
          950: "#070A11",
          900: "#0B0F19",
          850: "#0E1424",
          800: "#141C30",
          700: "#1E293B",
        },
        neon: {
          cyan: "#22D3EE",
          cyanGlow: "#67E8F9",
          purple: "#7C4DFF",
          purpleGlow: "#A78BFA",
          magenta: "#D946EF",
          emerald: "#10B981",
          amber: "#F59E0B",
        },
        hairline: {
          DEFAULT: "rgba(148, 163, 184, 0.14)",
          strong: "rgba(148, 163, 184, 0.24)",
        },
      },
      boxShadow: {
        "neon-cyan": "0 0 15px -2px rgba(34, 211, 238, 0.45), 0 0 6px -1px rgba(8, 145, 178, 0.6)",
        "neon-purple":
          "0 0 18px -2px rgba(124, 77, 255, 0.45), 0 0 6px -1px rgba(167, 139, 250, 0.6)",
        "neon-emerald":
          "0 0 15px -2px rgba(16, 185, 129, 0.45), 0 0 6px -1px rgba(52, 211, 153, 0.6)",
        "neon-card":
          "0 4px 20px -2px rgba(0, 0, 0, 0.7), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)",
        "neon-magenta":
          "0 0 18px -4px rgba(217, 70, 239, 0.55), 0 0 6px -2px rgba(217, 70, 239, 0.5)",
        panel: "0 18px 40px -24px rgba(0, 0, 0, 0.9), inset 0 1px 0 0 rgba(255, 255, 255, 0.04)",
        "panel-lg":
          "0 30px 70px -30px rgba(0, 0, 0, 0.95), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)",
        focus: "0 0 0 2px #070A11, 0 0 0 4px rgba(124, 77, 255, 0.9)",
        "laqta-glow": "0 10px 30px -12px rgba(124, 77, 255, 0.55)",
      },
      borderRadius: {
        card: "1rem",
        control: "0.75rem",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
