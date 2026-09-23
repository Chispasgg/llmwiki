"use client";

import * as React from "react";
import { fetchBranding, type Branding } from "@/lib/branding";

// Module-level singleton cache: avoids refetching on every component mount.
// Shared across all useBranding() callers in the same page session.
let _cache: Branding | null = null;
let _promise: Promise<Branding> | null = null;

function getOrFetch(): Promise<Branding> {
  if (_cache) return Promise.resolve(_cache);
  if (!_promise) {
    _promise = fetchBranding().then((b) => {
      _cache = b;
      _promise = null;
      return b;
    });
  }
  return _promise;
}

/**
 * Invalidates the module-level branding cache so the next useBranding() mount
 * (or the next component that re-runs its effect) will re-fetch from the API.
 * Safe to call at any time, including while a fetch is in flight.
 */
export function invalidateBrandingCache(): void {
  _cache = null;
  _promise = null;
}

export interface UseBrandingResult {
  branding: Branding | null;
  loading: boolean;
}

/**
 * Client hook that fetches branding once and caches it for the session.
 * Uses a module singleton so multiple mounts do not trigger multiple requests.
 */
export function useBranding(): UseBrandingResult {
  const [branding, setBranding] = React.useState<Branding | null>(_cache);
  const [loading, setLoading] = React.useState(_cache === null);

  React.useEffect(() => {
    if (_cache) {
      setBranding(_cache);
      setLoading(false);
      return;
    }
    let cancelled = false;
    getOrFetch().then((b) => {
      if (!cancelled) {
        setBranding(b);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { branding, loading };
}
