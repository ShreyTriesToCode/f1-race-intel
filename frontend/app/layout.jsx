import "./globals.css";

export const metadata = {
  title: "Race Intel | F1 Predictions",
  description: "Clean Sprint and Race prediction dashboard powered by GitHub Actions data.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
