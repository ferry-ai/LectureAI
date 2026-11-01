/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f3eee6",
        ink: "#1c1915",
        copper: "#c45c26",
        pine: "#1e3a34",
        rule: "#e4dccf",
        mist: "#f7f3ec",
      },
      fontFamily: {
        sans: ["Figtree", "sans-serif"],
        display: ["Fraunces", "serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(28, 25, 21, 0.04), 0 12px 30px rgba(28, 25, 21, 0.06)",
      },
    },
  },
  plugins: [],
};
