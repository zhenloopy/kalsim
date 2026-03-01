/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          0: "#0a0a0f",
          1: "#12121a",
          2: "#1a1a25",
          3: "#222230",
        },
        accent: {
          green: "#22c55e",
          red: "#ef4444",
          yellow: "#eab308",
          blue: "#3b82f6",
          cyan: "#06b6d4",
        },
      },
    },
  },
  plugins: [],
};
