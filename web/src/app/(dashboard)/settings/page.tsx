"use client";

import * as React from "react";
import { Copy, Check, ArrowLeft, Plus, Trash2, Key } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { buildApiKeyMcpConfig, MCP_URL } from "@/lib/mcp";

interface Usage {
  total_pages: number;
  total_storage_bytes: number;
  document_count: number;
  max_pages: number;
  max_storage_bytes: number;
}

interface ApiKey {
  id: string;
  name: string | null;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

interface NewKeyResult extends ApiKey {
  key: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / Math.pow(1024, i);
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function SettingsPage() {
  const router = useRouter();
  const [usage, setUsage] = React.useState<Usage | null>(null);
  const [keys, setKeys] = React.useState<ApiKey[]>([]);
  const [newKeyResult, setNewKeyResult] = React.useState<NewKeyResult | null>(
    null,
  );
  const [newKeyName, setNewKeyName] = React.useState("");
  const [creating, setCreating] = React.useState(false);
  const [showCreateForm, setShowCreateForm] = React.useState(false);
  const [configCopied, setConfigCopied] = React.useState(false);
  const [keyCopied, setKeyCopied] = React.useState(false);
  const [revoking, setRevoking] = React.useState<string | null>(null);

  const isHosted = process.env.NEXT_PUBLIC_MODE !== "local";

  React.useEffect(() => {
    apiFetch<Usage>("/v1/usage")
      .then((u) => setUsage(u))
      .catch((err) => console.error("Failed to load usage:", err));
    if (isHosted) {
      apiFetch<ApiKey[]>("/v1/api-keys")
        .then((k) => setKeys(k))
        .catch((err) => console.error("Failed to load API keys:", err));
    }
  }, [isHosted]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const result = await apiFetch<NewKeyResult>("/v1/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newKeyName.trim() || "Default" }),
      });
      setNewKeyResult(result);
      setKeys((prev) => [result, ...prev]);
      setShowCreateForm(false);
      setNewKeyName("");
    } catch {
      console.error("Failed to create key");
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    setRevoking(keyId);
    try {
      await apiFetch(`/v1/api-keys/${keyId}`, { method: "DELETE" });
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
      if (newKeyResult?.id === keyId) setNewKeyResult(null);
    } catch {
      console.error("Failed to revoke key");
    } finally {
      setRevoking(null);
    }
  };

  const handleCopyConfig = async (key: string) => {
    try {
      await navigator.clipboard.writeText(buildApiKeyMcpConfig(key));
      setConfigCopied(true);
      setTimeout(() => setConfigCopied(false), 2000);
    } catch {
      console.error("Failed to copy");
    }
  };

  const handleCopyKey = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key);
      setKeyCopied(true);
      setTimeout(() => setKeyCopied(false), 2000);
    } catch {
      console.error("Failed to copy");
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="flex items-center gap-3 mb-8">
        <button
          onClick={() => router.back()}
          className="p-1 rounded-md hover:bg-accent transition-colors cursor-pointer text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
        </button>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
      </div>

      {/* Usage */}
      {usage && (
        <section>
          <h2 className="text-base font-medium">Usage</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {usage.document_count} document
            {usage.document_count !== 1 ? "s" : ""} uploaded
          </p>
          <div className="mt-4 space-y-4">
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-muted-foreground">Storage</span>
                <span className="font-mono text-xs">
                  {formatBytes(usage.total_storage_bytes)} /{" "}
                  {formatBytes(usage.max_storage_bytes)}
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    usage.total_storage_bytes / usage.max_storage_bytes > 0.9
                      ? "bg-destructive"
                      : usage.total_storage_bytes / usage.max_storage_bytes >
                          0.7
                        ? "bg-yellow-500"
                        : "bg-primary",
                  )}
                  style={{
                    width: `${Math.min(100, (usage.total_storage_bytes / usage.max_storage_bytes) * 100)}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-muted-foreground">OCR Pages</span>
                <span className="font-mono text-xs">
                  {usage.total_pages.toLocaleString()} /{" "}
                  {usage.max_pages.toLocaleString()}
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    usage.total_pages / usage.max_pages > 0.9
                      ? "bg-destructive"
                      : usage.total_pages / usage.max_pages > 0.7
                        ? "bg-yellow-500"
                        : "bg-primary",
                  )}
                  style={{
                    width: `${Math.min(100, (usage.total_pages / usage.max_pages) * 100)}%`,
                  }}
                />
              </div>
            </div>
          </div>
        </section>
      )}

      {isHosted && (
        <>
          {usage && <div className="h-px bg-border my-8" />}

          {/* API Keys */}
          <section>
            <div className="flex items-center justify-between">
              <h2 className="text-base font-medium">API Keys</h2>
              {!showCreateForm && (
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border bg-background hover:bg-accent text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <Plus size={12} />
                  New key
                </button>
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Use API keys to connect MCP clients like Claude Desktop or Claude
              Code.
            </p>

            {showCreateForm && (
              <form
                onSubmit={handleCreateKey}
                className="mt-4 flex items-center gap-2"
              >
                <input
                  type="text"
                  placeholder="Key name (e.g. Claude Desktop)"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={creating}
                  className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateForm(false);
                    setNewKeyName("");
                  }}
                  className="px-3 py-1.5 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              </form>
            )}

            {/* New key reveal */}
            {newKeyResult && (
              <div className="mt-4 rounded-lg border border-border bg-muted/40 p-4 space-y-3">
                <div className="flex items-start gap-2">
                  <Key
                    size={14}
                    className="mt-0.5 text-muted-foreground shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">
                      {newKeyResult.name || "API Key"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Copy this key now — it won&apos;t be shown again.
                    </p>
                    <code className="mt-2 block text-xs font-mono bg-background border border-border rounded px-2 py-1.5 break-all">
                      {newKeyResult.key}
                    </code>
                  </div>
                  <button
                    onClick={() => handleCopyKey(newKeyResult.key)}
                    className={cn(
                      "flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors cursor-pointer shrink-0",
                      keyCopied
                        ? "bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400"
                        : "border-border bg-background text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {keyCopied ? (
                      <>
                        <Check size={11} />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy size={11} />
                        Copy
                      </>
                    )}
                  </button>
                </div>

                {/* MCP config for the new key */}
                <div>
                  <p className="text-xs text-muted-foreground mb-1.5">
                    MCP config for this key:
                  </p>
                  <div className="relative">
                    <pre className="rounded-md bg-background border border-border p-3 text-xs font-mono overflow-x-auto">
                      {buildApiKeyMcpConfig(newKeyResult.key)}
                    </pre>
                    <button
                      onClick={() => handleCopyConfig(newKeyResult.key)}
                      className={cn(
                        "absolute top-2 right-2 flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors cursor-pointer",
                        configCopied
                          ? "bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400"
                          : "border-border bg-background text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {configCopied ? (
                        <>
                          <Check size={11} />
                          Copied
                        </>
                      ) : (
                        <>
                          <Copy size={11} />
                          Copy
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <button
                  onClick={() => setNewKeyResult(null)}
                  className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline cursor-pointer"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Key list */}
            {keys.length > 0 && (
              <ul className="mt-4 divide-y divide-border rounded-lg border border-border overflow-hidden">
                {keys.map((k) => (
                  <li
                    key={k.id}
                    className="flex items-center gap-3 px-4 py-3 bg-background"
                  >
                    <Key size={14} className="text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {k.name || "Unnamed key"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        <code className="font-mono">{k.key_prefix}…</code>
                        {" · "}Created {formatDate(k.created_at)}
                        {k.last_used_at && (
                          <> · Last used {formatDate(k.last_used_at)}</>
                        )}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRevoke(k.id)}
                      disabled={revoking === k.id}
                      className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer disabled:opacity-50"
                      title="Revoke key"
                    >
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {keys.length === 0 && !showCreateForm && !newKeyResult && (
              <p className="mt-4 text-sm text-muted-foreground">
                No API keys yet.
              </p>
            )}

            <p className="mt-3 text-xs text-muted-foreground">
              MCP URL:{" "}
              <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
                {MCP_URL}
              </code>
            </p>
          </section>
        </>
      )}

      {!isHosted && (
        <>
          {usage && <div className="h-px bg-border my-8" />}
          <section>
            <h2 className="text-base font-medium">Connect Claude</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Run this command to get the Claude Desktop / Claude Code MCP
              config for this workspace:
            </p>
            <pre className="mt-4 rounded-lg bg-muted border border-border p-4 text-sm font-mono overflow-x-auto text-foreground">
              llmwiki mcp-config &lt;workspace-path&gt;
            </pre>
          </section>
        </>
      )}
    </div>
  );
}
