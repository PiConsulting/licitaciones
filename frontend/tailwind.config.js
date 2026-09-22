import forms from "@tailwindcss/forms";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        cedi: {
          celeste: "#0099DB",
          navy: "#003C6B",
          electric: "#2F4EF8",
          violet: "#A966FF",
          mint: "#7FF3DE",
          white: "#FFFFFF",
          "surface-tint": "#F4F9FC",
          "navy-68": "rgba(0,60,107,.68)",
          "navy-55": "rgba(0,60,107,.55)",
          "navy-30": "rgba(0,60,107,.3)",
          "navy-20": "rgba(0,60,107,.2)",
          "navy-12": "rgba(0,60,107,.12)",
          "navy-10": "rgba(0,60,107,.1)",
          "white-75": "rgba(255,255,255,.75)",
          "white-72": "rgba(255,255,255,.72)",
          "focus-ring": "rgba(0,153,219,.2)",
          "gradient-accent": "linear-gradient(90deg,#0099DB,#2F4EF8,#A966FF)",
          "gradient-button": "linear-gradient(90deg,#2F4EF8,#A966FF)",
          "gradient-icon": "linear-gradient(145deg,#0099DB,#2F4EF8)",
          "gradient-progress": "linear-gradient(90deg,#0099DB,#7FF3DE)",
        },
        cedia: {
          primary: "#2b6aae",
          light: "#75e1d2",
          turquoise: "#52a4ab",
          teal: "#3e8296",
        },
        pi: {
          black: "#101212",
          yellow: "#FFF100",
          pink: "#FD415A",
          orange: "#FF7A00",
          sky: "#93D3EF",
          blue: "#1F57E5",
          violet: "#7254DD",
        },
        primary: {
          DEFAULT: "var(--color-primary, #2563EB)",
          dark: "var(--color-primary-dark, #1D4ED8)",
          light: "var(--color-primary-light, #DBEAFE)",
          fg: "var(--color-primary-fg, #ffffff)",
        },
        success: {
          DEFAULT: "#10B981",
          light: "#D1FAE5",
        },
        warning: {
          DEFAULT: "#F59E0B",
          light: "#FEF3C7",
        },
        error: {
          DEFAULT: "#DC2626",
          light: "#FEE2E2",
        },
        critical: {
          DEFAULT: "#EA580C",
          light: "#FFEDD5",
        },
        highlight: {
          DEFAULT: "#4F46E5",
          light: "#E0E7FF",
        },
        info: {
          DEFAULT: "#3B82F6",
          light: "#DBEAFE",
        },
        gray: {
          50: "#F9FAFB",
          100: "#F3F4F6",
          200: "#E5E7EB",
          300: "#D1D5DB",
          400: "#9CA3AF",
          500: "#6B7280",
          600: "#4B5563",
          700: "#374151",
          900: "#111827",
        },
        background: "#F9FAFB",
        surface: "#FFFFFF",
      },
      fontFamily: {
        display: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["Montserrat", "system-ui", "sans-serif"],
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["Fira Code", "SF Mono", "Consolas", "monospace"],
      },
      spacing: {
        xs: "4px",
        sm: "8px",
        md: "16px",
        lg: "24px",
        xl: "32px",
        "2xl": "48px",
        "3xl": "64px",
      },
      borderRadius: {
        sm: "4px",
        md: "8px",
        lg: "12px",
        full: "9999px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(0, 0, 0, 0.05)",
        md: "0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)",
        lg: "0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)",
        xl: "0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)",
      },
      transitionDuration: {
        200: "200ms",
      },
      scale: {
        98: "0.98",
      },
    },
  },
  plugins: [forms],
};
