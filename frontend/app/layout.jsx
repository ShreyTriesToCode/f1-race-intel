import "./globals.css";

export const metadata = {
  title: "Race Intel | F1 Strategy Dashboard",
  description: "A free F1 strategy, prediction, weather, model-debug, and live race hub powered by GitHub Actions data.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
