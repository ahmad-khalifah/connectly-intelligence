import "@fontsource-variable/inter";
import "@fontsource/poppins/500.css";
import "@fontsource/poppins/600.css";
import "@fontsource/poppins/700.css";
import "./globals.css";

import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: { default: "Connectly Intelligence", template: "%s · Connectly Intelligence" },
  description:
    "Community intelligence for technology access in Nigeria. Every value is sourced; missing data is shown, not invented.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#6b1420" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-GB" className="h-full antialiased">
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
