import { apiFetch } from "@/lib/api";

export interface Branding {
  org_name: string | null;
  logo: string | null;
}

/**
 * Fetches the branding from the public API endpoint.
 * Never throws: returns a safe fallback on any error.
 */
export async function fetchBranding(): Promise<Branding> {
  try {
    return await apiFetch<Branding>("/v1/branding");
  } catch {
    return { org_name: null, logo: null };
  }
}

/**
 * Composes the page title from the org name.
 * Used by generateMetadata (T-006) and any title helper.
 */
export function orgTitle(org_name: string | null): string {
  return `${org_name ?? "LLM"} Wiki`;
}
