/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b1220",
        panel: "#111a2c",
        cyan: "#4fd1c5",
        amber: "#f6ad55",
      },
      boxShadow: {
        glow: "0 0 40px rgba(79, 209, 197, 0.08)",
      },
    },
  },
  plugins: [],
};
