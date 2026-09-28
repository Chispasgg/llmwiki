"use client";

import * as React from "react";
import { Download, Maximize2 } from "lucide-react";
import { DiagramViewer } from "./DiagramViewer";
import { sceneToSvg } from "@/components/wiki/excalidraw/ExcalidrawLoader";
import type { ExcalidrawScene } from "@/components/wiki/excalidraw/ExcalidrawLoader";

function downloadSvg(svg: string) {
  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `excalidraw-${Date.now()}.svg`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Parses the raw text of a ```excalidraw fenced block.
 * Returns a valid ExcalidrawScene or null if the JSON is missing/invalid.
 */
function parseScene(source: string): ExcalidrawScene | null {
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

export function ExcalidrawBlock({ source }: { source: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = React.useState<string | null>(null);
  const [fullscreen, setFullscreen] = React.useState(false);
  const [error, setError] = React.useState<"invalid" | "empty" | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const scene = parseScene(source);
    if (!scene) {
      setError("invalid");
      setSvgContent(null);
      return;
    }
    if (scene.elements.length === 0) {
      setError("empty");
      setSvgContent(null);
      return;
    }

    setError(null);

    sceneToSvg(scene)
      .then((svgEl) => {
        if (cancelled) return;
        const svgStr = svgEl.outerHTML;
        setSvgContent(svgStr);
        if (containerRef.current) {
          containerRef.current.innerHTML = svgStr;
        }
      })
      .catch(() => {
        if (!cancelled) setError("invalid");
      });

    return () => {
      cancelled = true;
    };
  }, [source]);

  // Degradación: JSON inválido o sin `elements`
  if (error === "invalid") {
    return (
      <pre className="text-[13px] leading-relaxed my-3 bg-muted/60 border border-border rounded-lg p-4 overflow-x-auto text-muted-foreground">
        {source}
      </pre>
    );
  }

  // Degradación: escena vacía
  if (error === "empty") {
    return (
      <div className="my-6 flex items-center justify-center text-sm text-muted-foreground border border-dashed border-border rounded-lg py-8">
        (diagrama vacío)
      </div>
    );
  }

  return (
    <>
      <div
        className="my-6 relative group"
        onClick={() => svgContent && setFullscreen(true)}
      >
        <div
          ref={containerRef}
          className="flex justify-center [&_svg]:max-w-full cursor-pointer"
        />
        {svgContent && (
          <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => {
                e.stopPropagation();
                downloadSvg(svgContent);
              }}
              className="p-1.5 rounded-md bg-background/80 border border-border text-muted-foreground hover:text-foreground cursor-pointer"
              title="Download SVG"
            >
              <Download className="size-3.5" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setFullscreen(true);
              }}
              className="p-1.5 rounded-md bg-background/80 border border-border text-muted-foreground hover:text-foreground cursor-pointer"
              title="View fullscreen"
            >
              <Maximize2 className="size-3.5" />
            </button>
          </div>
        )}
      </div>

      {fullscreen && svgContent && (
        <DiagramViewer
          content={svgContent}
          type="svg"
          onClose={() => setFullscreen(false)}
        />
      )}
    </>
  );
}
