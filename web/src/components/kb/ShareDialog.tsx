"use client";

import * as React from "react";
import { Loader2, Trash2, UserPlus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listShares,
  createShare,
  deleteShare,
  searchUsers,
  type KBShare,
  type UserSuggestion,
} from "@/lib/shares";

interface Props {
  kbId: string;
  kbName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ShareDialog({ kbId, kbName, open, onOpenChange }: Props) {
  const [shares, setShares] = React.useState<KBShare[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [accessLevel, setAccessLevel] = React.useState<"viewer" | "editor">(
    "viewer",
  );
  const [adding, setAdding] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [suggestions, setSuggestions] = React.useState<UserSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = React.useState(false);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setLoading(true);
    listShares(kbId)
      .then(setShares)
      .catch(() => setShares([]))
      .finally(() => setLoading(false));
  }, [open, kbId]);

  function handleEmailChange(val: string) {
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
  }

  function selectSuggestion(user: UserSuggestion) {
    setEmail(user.email);
    setSuggestions([]);
    setShowSuggestions(false);
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setError(null);
    setAdding(true);
    try {
      const share = await createShare(kbId, email.trim(), accessLevel);
      setShares((prev) => {
        const idx = prev.findIndex((s) => s.id === share.id);
        return idx >= 0
          ? prev.map((s) => (s.id === share.id ? share : s))
          : [...prev, share];
      });
      setEmail("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al compartir");
    } finally {
      setAdding(false);
    }
  }

  async function handleRevoke(share: KBShare) {
    try {
      await deleteShare(kbId, share.id);
      setShares((prev) => prev.filter((s) => s.id !== share.id));
    } catch {
      // ignore
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">
            Compartir &ldquo;{kbName}&rdquo;
          </DialogTitle>
        </DialogHeader>

        {/* Invite form */}
        <form onSubmit={handleAdd} className="flex gap-2 items-end mt-1">
          <div className="relative flex-1">
            <input
              type="text"
              value={email}
              onChange={(e) => handleEmailChange(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setShowSuggestions(false)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              placeholder="Email o nombre del usuario"
              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              autoComplete="off"
            />
            {showSuggestions && (
              <div className="absolute top-full left-0 right-0 z-50 mt-1 rounded-md border border-input bg-popover shadow-md overflow-hidden">
                {suggestions.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    onMouseDown={() => selectSuggestion(user)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                  >
                    <span className="font-medium">{user.display_name}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {user.email}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <select
            value={accessLevel}
            onChange={(e) =>
              setAccessLevel(e.target.value as "viewer" | "editor")
            }
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
          >
            <option value="viewer">Ver</option>
            <option value="editor">Editar</option>
          </select>
          <button
            type="submit"
            disabled={adding || !email.trim()}
            className="flex items-center gap-1.5 rounded-md bg-primary text-primary-foreground px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            {adding ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <UserPlus className="size-3.5" />
            )}
            Invitar
          </button>
        </form>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {/* Shares list */}
        <div className="mt-2 space-y-1">
          {loading && (
            <div className="flex justify-center py-4">
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {!loading && shares.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-3">
              Esta wiki no está compartida con nadie todavía.
            </p>
          )}
          {shares.map((share) => (
            <div
              key={share.id}
              className="flex items-center justify-between rounded-md px-3 py-2 bg-muted/40 text-sm"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-xs">
                  {share.shared_with_email}
                </p>
                <p className="text-[11px] text-muted-foreground capitalize">
                  {share.access_level === "viewer"
                    ? "Solo ver"
                    : "Puede editar"}
                </p>
              </div>
              <button
                onClick={() => handleRevoke(share)}
                className="ml-2 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                title="Revocar acceso"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
