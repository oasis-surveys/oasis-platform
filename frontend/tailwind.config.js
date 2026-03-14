/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        oasis: {
          50: "#E6F5F5",
          100: "#CCE9E9",
          200: "#99D4D4",
          300: "#4DB8B8",
          400: "#0F8B8F",
          500: "#0D7377",   // PRIMARY
          600: "#095B5E",
          700: "#074648",
          800: "#053335",
          900: "#031F20",
        },
        sand: {
          50: "#FAFAF7",    // page bg
          100: "#F5F0E8",
          200: "#F0EBE3",   // light sand
          300: "#F5E6C8",   // warm sand / accent warm
          400: "#E8D4A0",
          500: "#D4A843",   // ACCENT GOLD
          600: "#B88D2E",
          700: "#8C6B22",
          800: "#604A18",
        },
        charcoal: {
          DEFAULT: "#1A1A2E",
          700: "#4A4A5A",
        },
        terracotta: {
          DEFAULT: "#C44536",
          50: "#FDF2F1",
          100: "#FAD5D1",
        },
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-out": {
          "0%": { opacity: "1", transform: "translateY(0)" },
          "100%": { opacity: "0", transform: "translateY(8px)" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          "0%": { opacity: "0", transform: "translateY(-16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "orb-breathe": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.6" },
          "50%": { transform: "scale(1.06)", opacity: "0.9" },
        },
        "orb-glow": {
          "0%, 100%": { boxShadow: "0 0 40px rgba(var(--orb-rgb), 0.15)" },
          "50%": { boxShadow: "0 0 60px rgba(var(--orb-rgb), 0.3)" },
        },
        "voice-bar": {
          "0%, 100%": { transform: "scaleY(0.3)" },
          "50%": { transform: "scaleY(1)" },
        },
        "toast-in": {
          "0%": { opacity: "0", transform: "translateY(16px) scale(0.96)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "tooltip-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "spotlight": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "ring-expand": {
          "0%": { transform: "scale(0.8)", opacity: "0.6" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.3s ease-out",
        "fade-out": "fade-out 0.3s ease-out",
        "slide-up": "slide-up 0.4s ease-out",
        "slide-down": "slide-down 0.4s ease-out",
        "scale-in": "scale-in 0.25s ease-out",
        "orb-breathe": "orb-breathe 4s ease-in-out infinite",
        "orb-glow": "orb-glow 3s ease-in-out infinite",
        "toast-in": "toast-in 0.35s ease-out",
        "tooltip-in": "tooltip-in 0.15s ease-out",
        "spotlight": "spotlight 0.3s ease-out",
        "ring-expand": "ring-expand 2s ease-out infinite",
      },
    },
  },
  plugins: [],
};
