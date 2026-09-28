import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AMT Charting Tool",
  description: "Auction Market Theory charting and paper-trading web app",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
