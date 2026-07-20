"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import { useUserStore } from "@/stores";
import type { KnowledgeBase, Workspace } from "@/lib/types";

export function ShareWorkspaceDialog({
  workspace,
  open,
  onOpenChange,
}: {
  workspace: Workspace | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const user = useUserStore((s) => s.user);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("member");
  const [accessLevel, setAccessLevel] = React.useState("viewer");
  const [myWikis, setMyWikis] = React.useState<KnowledgeBase[]>([]);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [done, setDone] = React.useState("");

  React.useEffect(() => {
    if (!open || !workspace || !user) return;
    setEmail("");
    setError("");
    setDone("");
    setMyWikis([]);
    setSelected(new Set());
    setRole("member");
    setAccessLevel("viewer");
    apiFetch<KnowledgeBase[]>(`/v1/workspaces/${workspace.id}/wikis`)
      .then((all) => {
        const mine = all.filter((kb) => kb.user_id === user.id);
        setMyWikis(mine);
        setSelected(new Set(mine.map((kb) => kb.id))); // todas marcadas por defecto
      })
      .catch(() => {
        setMyWikis([]);
        setSelected(new Set());
      });
  }, [open, workspace, user]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleShare = async () => {
    if (!workspace || !email.trim()) return;
    setSaving(true);
    setError("");
    setDone("");
    try {
      await apiFetch(`/v1/workspaces/${workspace.id}/share`, {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          role,
          access_level: accessLevel,
          kb_ids: Array.from(selected),
        }),
      });
      setDone(`Compartido con ${email.trim()}.`);
      setEmail("");
    } catch (err) {
      setError((err as Error).message || "No se pudo compartir");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Compartir &ldquo;{workspace?.name}&rdquo;</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@dominio.com"
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            autoFocus
          />
          <div className="flex gap-2">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="member">Rol: miembro</option>
              <option value="admin">Rol: admin</option>
            </select>
            <select
              value={accessLevel}
              onChange={(e) => setAccessLevel(e.target.value)}
              className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="viewer">Wikis: solo lectura</option>
              <option value="editor">Wikis: edición</option>
            </select>
          </div>

          <div>
            <p className="text-xs text-muted-foreground mb-1.5">
              Mis wikis de este workspace ({selected.size}/{myWikis.length})
            </p>
            {myWikis.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No tienes wikis en este workspace.
              </p>
            ) : (
              <ul className="max-h-48 overflow-y-auto rounded-lg border border-input divide-y">
                {myWikis.map((kb) => (
                  <li key={kb.id} className="px-3 py-2">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selected.has(kb.id)}
                        onChange={() => toggle(kb.id)}
                      />
                      {kb.name}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {done && <p className="text-sm text-muted-foreground">{done}</p>}
        </div>

        <DialogFooter>
          <button
            onClick={handleShare}
            disabled={saving || !email.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {saving ? "Compartiendo..." : "Compartir"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
