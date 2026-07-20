"use client";

import * as React from "react";
import { Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/types";

type Share = {
  id: string;
  kb_id: string;
  shared_with_id: string;
  shared_with_email: string;
  shared_with_display_name: string;
  access_level: string;
  created_at: string;
};

export function ShareWikiDialog({
  kb,
  open,
  onOpenChange,
}: {
  kb: KnowledgeBase | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [shares, setShares] = React.useState<Share[]>([]);
  const [email, setEmail] = React.useState("");
  const [accessLevel, setAccessLevel] = React.useState("viewer");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const load = React.useCallback(() => {
    if (!kb) return;
    apiFetch<Share[]>(`/v1/knowledge-bases/${kb.id}/shares`)
      .then(setShares)
      .catch(() => setShares([]));
  }, [kb]);

  React.useEffect(() => {
    if (!open || !kb) return;
    setEmail("");
    setError("");
    setShares([]);
    load();
  }, [open, kb, load]);

  const handleAdd = async () => {
    if (!kb || !email.trim()) return;
    setBusy(true);
    setError("");
    try {
      await apiFetch(`/v1/knowledge-bases/${kb.id}/shares`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), access_level: accessLevel }),
      });
      setEmail("");
      load();
    } catch (err) {
      setError((err as Error).message || "No se pudo compartir");
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (shareId: string) => {
    if (!kb) return;
    setBusy(true);
    setError("");
    try {
      await apiFetch(`/v1/knowledge-bases/${kb.id}/shares/${shareId}`, {
        method: "DELETE",
      });
      load();
    } catch (err) {
      setError((err as Error).message || "No se pudo quitar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Compartir &ldquo;{kb?.name}&rdquo;</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@dominio.com"
              className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm"
            />
            <select
              value={accessLevel}
              onChange={(e) => setAccessLevel(e.target.value)}
              className="rounded-lg border border-input bg-background px-2 py-2 text-sm"
            >
              <option value="viewer">Lectura</option>
              <option value="editor">Edición</option>
            </select>
            <button
              onClick={handleAdd}
              disabled={busy || !email.trim()}
              className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              Añadir
            </button>
          </div>

          {shares.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Esta wiki no está compartida con nadie.
            </p>
          ) : (
            <ul className="rounded-lg border border-input divide-y max-h-56 overflow-y-auto">
              {shares.map((s) => (
                <li
                  key={s.id}
                  className="px-3 py-2 flex items-center justify-between gap-2"
                >
                  <span className="text-sm">
                    {s.shared_with_display_name || s.shared_with_email}
                    <span className="text-xs text-muted-foreground ml-2">
                      {s.access_level === "editor" ? "edición" : "lectura"}
                    </span>
                  </span>
                  <button
                    onClick={() => handleRemove(s.id)}
                    disabled={busy}
                    aria-label="Quitar acceso"
                    className="p-1 rounded hover:bg-destructive/10 hover:text-destructive text-muted-foreground cursor-pointer disabled:opacity-50"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
