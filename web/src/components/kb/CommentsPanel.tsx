"use client";

import * as React from "react";
import {
  X,
  Check,
  RotateCcw,
  Trash2,
  Pencil,
  MessageSquarePlus,
} from "lucide-react";
import { toast } from "sonner";
import { useComments } from "@/hooks/useComments";
import { scrollToAndFlash } from "@/lib/highlight";

export function CommentsPanel({
  docId,
  wikiContentRef,
  onClose,
}: {
  docId: string | null;
  wikiContentRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
}) {
  const c = useComments(docId);
  const [newBody, setNewBody] = React.useState("");
  const [selection, setSelection] = React.useState("");
  const [editing, setEditing] = React.useState<string | null>(null);
  const [editBody, setEditBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  // Captura la selección de texto dentro del contenido de la wiki.
  React.useEffect(() => {
    const el = wikiContentRef.current;
    if (!el) return;
    const onMouseUp = () => {
      const sel = window.getSelection();
      const text = sel ? sel.toString().trim() : "";
      if (text && sel && el.contains(sel.anchorNode)) setSelection(text);
    };
    el.addEventListener("mouseup", onMouseUp);
    return () => el.removeEventListener("mouseup", onMouseUp);
  }, [wikiContentRef]);

  const submit = async () => {
    if (!newBody.trim()) return;
    setBusy(true);
    try {
      await c.create(newBody.trim(), selection || null);
      setNewBody("");
      setSelection("");
      toast.success("Comentario añadido");
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : "No se pudo crear el comentario",
      );
    } finally {
      setBusy(false);
    }
  };

  const wrap = (fn: () => Promise<void>) => async () => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="w-80 shrink-0 border-l border-border h-full flex flex-col bg-background">
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-sm font-semibold">Comentarios</span>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted-foreground flex items-center gap-1">
            <input
              type="checkbox"
              checked={c.showResolved}
              onChange={(e) => c.setShowResolved(e.target.checked)}
            />
            Ver cerrados
          </label>
          <button
            onClick={onClose}
            aria-label="Cerrar panel"
            className="p-1 rounded hover:bg-accent cursor-pointer"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      <div className="p-3 border-b space-y-2">
        {selection ? (
          <p className="text-xs text-muted-foreground">
            Anclado a:{" "}
            <span className="italic">
              "{selection.slice(0, 80)}
              {selection.length > 80 ? "…" : ""}"
            </span>
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Selecciona texto en la página para anclar, o deja sin anclar.
          </p>
        )}
        <textarea
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          placeholder="Escribe un comentario…"
          rows={3}
          className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm resize-none"
        />
        <button
          onClick={submit}
          disabled={busy || !newBody.trim()}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-50 cursor-pointer"
        >
          <MessageSquarePlus className="size-3.5" /> Añadir
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {c.loading ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">Cargando…</p>
        ) : c.comments.length === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">
            Sin comentarios.
          </p>
        ) : (
          <ul>
            {c.comments.map((cm) => (
              <li key={cm.id} className="px-3 py-2 border-b last:border-0">
                {cm.target_text && (
                  <button
                    onClick={() => {
                      const found = scrollToAndFlash(
                        wikiContentRef.current,
                        cm.target_text,
                      );
                      if (!found)
                        toast.info(
                          "El texto anclado ya no está en la página (sin ancla).",
                        );
                    }}
                    className="block text-left text-xs text-muted-foreground italic hover:text-foreground mb-1 cursor-pointer"
                  >
                    "{cm.target_text.slice(0, 90)}
                    {cm.target_text.length > 90 ? "…" : ""}"
                  </button>
                )}
                {editing === cm.id ? (
                  <div className="space-y-1">
                    <textarea
                      value={editBody}
                      onChange={(e) => setEditBody(e.target.value)}
                      rows={2}
                      className="w-full rounded-md border border-input bg-background px-2 py-1 text-sm resize-none"
                    />
                    <div className="flex gap-1">
                      <button
                        onClick={wrap(async () => {
                          await c.edit(cm.id, editBody.trim());
                          setEditing(null);
                        })}
                        disabled={busy || !editBody.trim()}
                        className="px-2 py-1 text-xs bg-primary text-primary-foreground rounded disabled:opacity-50 cursor-pointer"
                      >
                        Guardar
                      </button>
                      <button
                        onClick={() => setEditing(null)}
                        className="px-2 py-1 text-xs border rounded cursor-pointer"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <p
                    className={`text-sm ${cm.status === "resolved" ? "line-through text-muted-foreground" : "text-foreground"}`}
                  >
                    {cm.body}
                  </p>
                )}
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <span>{cm.author_name ?? "—"}</span>
                  <span className="ml-auto flex items-center gap-1">
                    {editing !== cm.id && (
                      <button
                        onClick={() => {
                          setEditing(cm.id);
                          setEditBody(cm.body);
                        }}
                        aria-label="Editar"
                        className="p-1 rounded hover:bg-accent cursor-pointer"
                      >
                        <Pencil className="size-3.5" />
                      </button>
                    )}
                    {cm.status === "open" ? (
                      <button
                        onClick={wrap(() => c.resolve(cm.id))}
                        aria-label="Cerrar"
                        className="p-1 rounded hover:bg-accent cursor-pointer"
                      >
                        <Check className="size-3.5" />
                      </button>
                    ) : (
                      <button
                        onClick={wrap(() => c.reopen(cm.id))}
                        aria-label="Reabrir"
                        className="p-1 rounded hover:bg-accent cursor-pointer"
                      >
                        <RotateCcw className="size-3.5" />
                      </button>
                    )}
                    <button
                      onClick={wrap(() => c.remove(cm.id))}
                      aria-label="Borrar"
                      className="p-1 rounded hover:bg-accent cursor-pointer text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
