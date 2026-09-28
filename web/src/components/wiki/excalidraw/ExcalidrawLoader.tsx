"use client";

/**
 * ExcalidrawLoader
 *
 * Client-only wrapper for Excalidraw. Excalidraw accesses `window` at import
 * time and cannot be rendered on the server. All exports from this module are
 * safe to import in any Client Component; never import this file from a Server
 * Component or from code that runs during SSR.
 *
 * Consumers (DG-002 / DG-003):
 *   import { ExcalidrawCanvas, sceneToSvg } from "@/components/wiki/excalidraw/ExcalidrawLoader";
 *   import type { ExcalidrawScene } from "@/components/wiki/excalidraw/ExcalidrawLoader";
 */

import "@excalidraw/excalidraw/index.css";
import dynamic from "next/dynamic";
import type { ExcalidrawElement, NonDeleted } from "@excalidraw/excalidraw/element/types";
import type { BinaryFiles, AppState } from "@excalidraw/excalidraw/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Minimal snapshot of an Excalidraw scene.
 * Pass this between components and persist it to the API.
 */
export type ExcalidrawScene = {
  elements: readonly ExcalidrawElement[];
  appState?: Partial<AppState>;
  files?: BinaryFiles | null;
};

// ---------------------------------------------------------------------------
// Dynamic component
// ---------------------------------------------------------------------------

/**
 * Excalidraw editor component, loaded only in the browser.
 * Accepts the same props as the upstream `Excalidraw` component.
 *
 * Usage:
 *   <ExcalidrawCanvas initialData={scene} onChange={handleChange} />
 */
export const ExcalidrawCanvas = dynamic(
  () => import("@excalidraw/excalidraw").then((m) => m.Excalidraw),
  { ssr: false },
);

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Convert an Excalidraw scene to an SVG element.
 *
 * Uses a dynamic import so the heavy Excalidraw bundle is never included in
 * the server bundle. Always call this from client-side code only.
 *
 * @returns SVGSVGElement ready to be appended to the DOM or serialised.
 */
export async function sceneToSvg(scene: ExcalidrawScene): Promise<SVGSVGElement> {
  const { exportToSvg } = await import("@excalidraw/excalidraw");
  return exportToSvg({
    elements: scene.elements as readonly NonDeleted<ExcalidrawElement>[],
    appState: scene.appState as Partial<Omit<AppState, "offsetTop" | "offsetLeft">>,
    files: scene.files ?? null,
  });
}
