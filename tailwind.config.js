/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",  // your HTML files
    "./app/static/js/**/*.js"     // optional: if you use Tailwind in JS
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}