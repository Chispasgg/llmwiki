import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { OpenReplayTracker } from "@/components/OpenReplay";
import { fetchBrandingServer } from "@/lib/branding-server";
import { orgTitle } from "@/lib/branding";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const DESCRIPTION =
  "Free, open-source implementation of Karpathy's LLM Wiki. Upload documents and build a compounding wiki directly via Claude.";

export async function generateMetadata(): Promise<Metadata> {
  const { org_name, logo } = await fetchBrandingServer();
  const title = orgTitle(org_name);

  return {
    title: {
      default: title,
      template: `%s · ${title}`,
    },
    description: DESCRIPTION,
    metadataBase: new URL("https://llmwiki.app"),
    // Only override icons when a custom logo is configured; otherwise Next.js
    // falls back to app/icon.svg automatically.
    ...(logo != null ? { icons: { icon: logo } } : {}),
    openGraph: {
      title,
      description: DESCRIPTION,
      url: "https://llmwiki.app",
      siteName: title,
      type: "website",
      images: [{ url: "/og.png", width: 1200, height: 630, alt: title }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: DESCRIPTION,
      images: ["/og.png"],
    },
  };
}

// Script to prevent theme flash - runs before React hydrates
// Must match the storageKey used by ThemeProvider (default is 'theme')
const themeScript = `
  (function() {
    try {
      var storageKey = 'theme';
      var stored = localStorage.getItem(storageKey);
      var isValid = stored === 'light' || stored === 'dark';
      var theme = isValid ? stored : 'light';

      // Persist a sane default so a refresh doesn't fall back to light/system
      if (!isValid) {
        localStorage.setItem(storageKey, theme);
      }

      document.documentElement.classList.remove('light', 'dark');
      document.documentElement.classList.add(theme);
      document.documentElement.style.colorScheme = theme;
    } catch (e) {
      document.documentElement.classList.add('light');
      document.documentElement.style.colorScheme = 'dark';
    }
  })();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: themeScript }}
          suppressHydrationWarning
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
          storageKey="theme"
        >
          {children}
          <Toaster richColors />
          <OpenReplayTracker />
        </ThemeProvider>
      </body>
    </html>
  );
}
