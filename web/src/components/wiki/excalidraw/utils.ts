/**
 * Shared pure utilities for Excalidraw scene handling.
 *
 * This module has NO dependency on the Excalidraw runtime — it is safe to
 * import from both Client Components and any code path that runs during SSR.
 * Keep it that way: never import from "@excalidraw/excalidraw" here.
 */

import type { ExcalidrawScene } from "./ExcalidrawLoader";

/**
 * Parses the raw text of a ```excalidraw fenced block.
 *
 * Accepts both the legacy format `{ elements, appState, files }` and the
 * canonical format produced by `serializeAsJSON`:
 * `{ type, version, source, elements, appState, files }`.
 *
 * Returns a valid ExcalidrawScene or null if the JSON is missing/invalid.
 */
export function parseScene(source: string): ExcalidrawScene | null {
  try {
    const parsed: unknown = JSON.parse(source);
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      !Array.isArray((parsed as Record<string, unknown>).elements)
    ) {
      return null;
    }
    return parsed as ExcalidrawScene;
  } catch {
    return null;
  }
}
