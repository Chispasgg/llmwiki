"use client";

import * as React from "react";
import { Download, Maximize2 } from "lucide-react";
import { DiagramViewer } from "./DiagramViewer";

function isDark() {
  return document.documentElement.classList.contains("dark");
}

function downloadSvg(svg: string) {
  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `diagram-${Date.now()}.svg`;
  a.click();
  URL.revokeObjectURL(url);
}

// Renderiza el diagrama con tema neutral (fondo blanco) para descarga/fullscreen.
async function renderNeutral(chart: string, id: string): Promise<string> {
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({ startOnLoad: false, theme: "neutral" });
  const { svg } = await mermaid.render(id, chart);
  return svg;
}

export function MermaidBlock({ chart }: { chart: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const idRef = React.useRef(
    `mermaid-${Math.random().toString(36).slice(2, 9)}`,
  );
  const [svgContent, setSvgContent] = React.useState<string | null>(null);
  const [lightSvg, setLightSvg] = React.useState<string | null>(null);
  const [fullscreen, setFullscreen] = React.useState(false);
  const [dark, setDark] = React.useState(false);

  React.useEffect(() => {
    setDark(isDark());
    const observer = new MutationObserver(() => setDark(isDark()));
    observer.observe(document.documentElement, { attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  // Renderiza la versión de display (respeta dark/light mode)
  React.useEffect(() => {
    let cancelled = false;
    import("mermaid").then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        theme: dark ? "dark" : "neutral",
      });
      mermaid
        .render(idRef.current, chart)
        .then(({ svg }) => {
          if (!cancelled) {
            setSvgContent(svg);
            if (containerRef.current) containerRef.current.innerHTML = svg;
          }
        })
        .catch(() => {
          if (!cancelled && containerRef.current)
            containerRef.current.textContent = chart;
        });
    });
    return () => {
      cancelled = true;
    };
  }, [chart, dark]);

  // Renderiza la versión neutral (blanca) para descarga y fullscreen
  React.useEffect(() => {
    let cancelled = false;
    const lightId = `${idRef.current}-light`;
    renderNeutral(chart, lightId)
      .then((svg) => {
        if (!cancelled) setLightSvg(svg);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [chart]);

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    downloadSvg(lightSvg ?? svgContent ?? "");
  };

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
              onClick={handleDownload}
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

      {fullscreen && (lightSvg || svgContent) && (
        <DiagramViewer
          content={lightSvg ?? svgContent!}
          type="svg"
          onClose={() => setFullscreen(false)}
        />
      )}
    </>
  );
}
