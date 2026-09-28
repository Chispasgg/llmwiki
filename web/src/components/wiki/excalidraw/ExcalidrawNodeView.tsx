"use client";

/**
 * ExcalidrawNodeView — React NodeView for the TipTap `excalidraw` node.
 *
 * Renders:
 *   - A static SVG preview of the diagram (via sceneToSvg).
 *   - An "Editar" button (+ double-click) that opens a full-screen modal.
 *   - The modal contains ExcalidrawCanvas (the live editor) with Save/Cancel.
 *
 * On Save:
 *   Captures the scene from the Excalidraw imperative API
 *   (api.getSceneElements() + api.getAppState() + api.getFiles()),
 *   serializes to JSON, and writes back to the node's `scene` attr via
 *   updateAttributes({ scene: <JSON> }). The tiptap-markdown serializer will
 *   then pick up the new value on the next getMarkdown() call.
 *
 * The modal is rendered via a React portal to document.body to keep it
 * outside ProseMirror's contenteditable subtree and avoid event conflicts.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { NodeViewWrapper } from "@tiptap/react";
import type { ReactNodeViewProps } from "@tiptap/react";
import { sceneToSvg, sceneToJson, ExcalidrawCanvas } from "./ExcalidrawLoader";
import type { ExcalidrawScene } from "./ExcalidrawLoader";
import { parseScene } from "./utils";
import type { ExcalidrawImperativeAPI, ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";

// ---------------------------------------------------------------------------
// ScenePreview — static SVG thumbnail
// ---------------------------------------------------------------------------

function ScenePreview({ scene }: { scene: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [error, setError] = React.useState<"invalid" | "empty" | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const parsed = parseScene(scene);
    if (!parsed) {
      setError("invalid");
      return;
    }
    if (parsed.elements.length === 0) {
      setError("empty");
      return;
    }

    setError(null);

    sceneToSvg(parsed)
      .then((svgEl) => {
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svgEl.outerHTML;
      })
      .catch(() => {
        if (!cancelled) setError("invalid");
      });

    return () => {
      cancelled = true;
    };
  }, [scene]);

  if (error === "empty") {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground py-10 select-none">
        (diagrama vacío — haz doble clic o pulsa Editar para empezar)
      </div>
    );
  }

  if (error === "invalid") {
    return (
      <pre className="text-xs text-muted-foreground bg-muted/60 p-3 rounded overflow-x-auto">
        {scene}
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex justify-center [&_svg]:max-w-full pointer-events-none"
    />
  );
}

// ---------------------------------------------------------------------------
// ExcalidrawEditor modal — renders inside a portal to document.body
// ---------------------------------------------------------------------------

interface EditorModalProps {
  scene: string;
  onSave: (api: ExcalidrawImperativeAPI) => Promise<void>;
  onCancel: () => void;
}

function EditorModal({ scene, onSave, onCancel }: EditorModalProps) {
  const apiRef = React.useRef<ExcalidrawImperativeAPI | null>(null);
  // True once the Excalidraw imperative API has been delivered (canvas mounted).
  // Guardar is disabled until then to prevent a silent no-op save.
  const [ready, setReady] = React.useState(false);

  const initialData = React.useMemo((): ExcalidrawInitialDataState | undefined => {
    const parsed = parseScene(scene);
    if (!parsed) return undefined;
    // ExcalidrawScene is structurally compatible with ExcalidrawInitialDataState.
    return parsed as unknown as ExcalidrawInitialDataState;
  }, [scene]);

  const handleSave = () => {
    if (apiRef.current) {
      void onSave(apiRef.current);
    }
  };

  // Close on backdrop click
  const handleBackdropMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onCancel();
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60"
      onMouseDown={handleBackdropMouseDown}
    >
      <div
        className="flex flex-col bg-background rounded-xl shadow-2xl w-[92vw] h-[88vh] max-w-[1400px] overflow-hidden"
        // Prevent backdrop mousedown from firing on inner clicks
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <span className="font-medium text-sm">Editar diagrama</span>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-sm border border-border rounded hover:bg-accent transition-colors cursor-pointer"
              type="button"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={!ready}
              className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              type="button"
            >
              Guardar
            </button>
          </div>
        </div>

        {/* Excalidraw canvas */}
        <div className="flex-1 min-h-0">
          <ExcalidrawCanvas
            initialData={initialData}
            excalidrawAPI={(api: ExcalidrawImperativeAPI) => {
              apiRef.current = api;
              setReady(true);
            }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// ExcalidrawNodeView — main NodeView component
// ---------------------------------------------------------------------------

export function ExcalidrawNodeView({
  node,
  updateAttributes,
  selected,
}: ReactNodeViewProps) {
  const [modalOpen, setModalOpen] = React.useState(false);
  const scene = (node.attrs as { scene: string }).scene;

  const openModal = () => setModalOpen(true);
  const closeModal = () => setModalOpen(false);

  const handleSave = async (api: ExcalidrawImperativeAPI): Promise<void> => {
    const elements = api.getSceneElements();
    const appState = api.getAppState();
    const files = api.getFiles();

    // serializeAsJSON strips non-serializable state (collaborators Map,
    // fileHandle, deleted elements) producing a reload-safe JSON string.
    // Using JSON.stringify directly would encode collaborators as {} causing
    // TypeError on re-open when Excalidraw calls collaborators.forEach().
    const sceneJson = await sceneToJson(elements, appState, files);
    updateAttributes({ scene: sceneJson });
    closeModal();
  };

  return (
    <NodeViewWrapper
      className={[
        "my-4 rounded-lg border transition-all",
        selected
          ? "border-primary ring-2 ring-primary/20"
          : "border-border",
      ].join(" ")}
    >
      {/* Preview area — double-click opens editor */}
      <div
        className="relative group cursor-pointer"
        onDoubleClick={openModal}
      >
        <ScenePreview scene={scene} />

        {/* Edit button — appears on hover */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openModal();
            }}
            className="px-2 py-1 text-xs bg-background/90 border border-border rounded shadow-sm hover:bg-accent transition-colors cursor-pointer"
          >
            Editar
          </button>
        </div>
      </div>

      {/* Modal rendered outside the editor via portal */}
      {modalOpen && (
        <EditorModal
          scene={scene}
          onSave={handleSave}
          onCancel={closeModal}
        />
      )}
    </NodeViewWrapper>
  );
}
