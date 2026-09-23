import type { Branding } from "@/lib/branding";

const BASE_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:1502";

/**
 * Server-side branding fetch used by generateMetadata in layout.tsx.
 *
 * Cache decision: `next: { revalidate: 60 }` — branding (logo / org name)
 * changes infrequently. A 60-second ISR window avoids hammering the API on
 * every SSR request while keeping the browser tab title and favicon reasonably
 * fresh after an admin update. Use `cache: "no-store"` instead if you need
 * instant propagation (at the cost of one extra API call per page render).
 *
 * Never throws: any network or non-ok response returns the safe fallback
 * so layout rendering is never blocked.
 */
export async function fetchBrandingServer(): Promise<Branding> {
  try {
    const res = await fetch(`${BASE_URL}/v1/branding`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(1500),
    });
    if (!res.ok) return { org_name: null, logo: null };
    return res.json() as Promise<Branding>;
  } catch {
    return { org_name: null, logo: null };
  }
}
