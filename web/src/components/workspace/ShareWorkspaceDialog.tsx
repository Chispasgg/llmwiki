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
import { searchUsers, type UserSuggestion } from "@/lib/shares";
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
  const [suggestions, setSuggestions] = React.useState<UserSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = React.useState(false);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  React.useEffect(() => {
    if (!open || !workspace || !user) return;
    setEmail("");
    setError("");
    setDone("");
    setSuggestions([]);
    setShowSuggestions(false);
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

  const handleEmailChange = (val: string) => {
    setEmail(val);
    setSuggestions([]);
    setShowSuggestions(false);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.length < 2) return;
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await searchUsers(val);
        setSuggestions(results);
        setShowSuggestions(results.length > 0);
      } catch {
        // ignore search errors
      }
    }, 300);
  };

  const selectSuggestion = (u: UserSuggestion) => {
    setEmail(u.email);
    setSuggestions([]);
    setShowSuggestions(false);
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
          <div className="relative">
            <input
              value={email}
              onChange={(e) => handleEmailChange(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setShowSuggestions(false)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              placeholder="Email o nombre del usuario"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
              autoComplete="off"
              autoFocus
            />
            {showSuggestions && (
              <div className="absolute top-full left-0 right-0 z-50 mt-1 rounded-md border border-input bg-popover shadow-md overflow-hidden">
                {suggestions.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onMouseDown={() => selectSuggestion(u)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                  >
                    <span className="font-medium">{u.display_name}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {u.email}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
