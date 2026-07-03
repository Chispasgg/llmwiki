"use client";

import * as React from "react";
import { fetchCommentHistory } from "@/hooks/useComments";
import type { CommentHistoryEntry } from "@/lib/types";

const ACTION_LABEL: Record<CommentHistoryEntry["action"], string> = {
  created: "Creado",
  edited: "Editado",
  resolved: "Cerrado",
  reopened: "Reabierto",
  deleted: "Borrado",
};

export function CommentsHistoryView({ kbId }: { kbId: string }) {
  const [rows, setRows] = React.useState<CommentHistoryEntry[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchCommentHistory(kbId).then((r) => {
      if (alive) {
        setRows(r);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [kbId]);

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <h1 className="text-xl font-bold mb-1">Comentarios</h1>
      <p className="text-sm text-muted-foreground mb-6">
        Historial de comentarios de esta wiki (solo lectura).
      </p>
      {loading ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Sin historial de comentarios.
        </p>
      ) : (
        <ul className="space-y-3">
          {rows.map((r, i) => (
            <li key={i} className="rounded-lg border border-border p-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <span className="font-medium text-foreground">
                  {ACTION_LABEL[r.action]}
                </span>
                <span>· {r.actor_name || "—"}</span>
                <span className="ml-auto">
                  {new Date(r.created_at).toLocaleString()}
                </span>
              </div>
              {r.doc_title && (
                <div className="text-xs text-muted-foreground mb-1">
                  Página: {r.doc_title}
                </div>
              )}
              {r.target_text && (
                <p className="text-xs italic text-muted-foreground mb-1">
                  "{r.target_text}"
                </p>
              )}
              <p className="text-sm text-foreground whitespace-pre-wrap">
                {r.body}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
