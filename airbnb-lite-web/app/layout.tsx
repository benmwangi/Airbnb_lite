import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Host pricing control | Airbnb-lite",
  description: "Review, approve, and override AI-recommended nightly pricing for your listings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
