"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  getChatPrompt,
  putChatPrompt,
  getChatStatus,
  getAiProviders,
  setActiveProvider,
  type ChatPromptAdmin,
  type ChatStatusAdmin,
  type AiProvidersResponse,
} from "@/lib/admin";
import { ProviderCard } from "./ProviderCard";

/** Must match the default in the backend (api/routers/superadmin/chat.py). */
const DEFAULT_CHAT_SYSTEM_PROMPT =
  "Eres un asistente que responde preguntas sobre esta wiki. Usa ÚNICAMENTE la información del CONTEXTO proporcionado. Cita las fuentes relevantes con [n] según su número. Si la respuesta no está en el contexto, dilo claramente y no inventes.";

const field =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono";

export default function AdminChatPage() {
  const [prompt, setPrompt] = useState<ChatPromptAdmin | null>(null);
  const [status, setStatus] = useState<ChatStatusAdmin | null>(null);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  // AI Providers
  const [aiProviders, setAiProviders] = useState<AiProvidersResponse | null>(
    null,
  );
  const [activating, setActivating] = useState(false);

  useEffect(() => {
    getChatPrompt()
      .then((data) => {
        setPrompt(data);
        setValue(data.system_prompt);
      })
      .catch(() => toast.error("No se pudo cargar el prompt del chat"));

    getChatStatus()
      .then(setStatus)
      .catch(() => {
        // Status is informational; failures are non-fatal.
      });

    getAiProviders()
      .then(setAiProviders)
      .catch(() =>
        toast.error("No se pudo cargar la configuración de proveedores IA"),
      );
  }, []);

  const handleActivate = async (provider: string) => {
    setActivating(true);
    try {
      const updated = await setActiveProvider(provider);
      setAiProviders(updated);
      toast.success(`Proveedor activo: ${provider}`);
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "Error al cambiar el proveedor activo";
      toast.error(msg);
    } finally {
      setActivating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await putChatPrompt(value);
      setPrompt(updated);
      setValue(updated.system_prompt);
      toast.success("Prompt del chat guardado");
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Error al guardar el prompt";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = () => {
    setValue(DEFAULT_CHAT_SYSTEM_PROMPT);
  };

  if (!prompt) {
    return <p className="text-sm text-muted-foreground">Cargando…</p>;
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-bold">IA / Chat</h1>

      {/* ── AI Providers ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Proveedores de IA</h2>

        {aiProviders ? (
          <>
            {/* Active provider selector */}
            <div className="rounded-lg border p-4 space-y-3">
              <p className="text-sm font-medium">Proveedor activo</p>
              <div className="flex flex-wrap gap-4">
                {aiProviders.providers.map((p) => (
                  <label
                    key={p.provider}
                    className="flex items-center gap-2 text-sm cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="active-provider"
                      value={p.provider}
                      checked={aiProviders.active_provider === p.provider}
                      onChange={() => handleActivate(p.provider)}
                      disabled={activating}
                      className="cursor-pointer"
                    />
                    <span className="capitalize">{p.provider}</span>
                  </label>
                ))}
              </div>
              {activating && (
                <p className="text-xs text-muted-foreground">
                  Cambiando proveedor…
                </p>
              )}
            </div>

            {/* One card per provider */}
            {aiProviders.providers.map((p) => (
              <ProviderCard
                key={p.provider}
                provider={p}
                isActive={aiProviders.active_provider === p.provider}
                onSaved={setAiProviders}
              />
            ))}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Cargando proveedores…
          </p>
        )}
      </section>

      <hr className="border-border" />

      {/* ── System Prompt ─────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Prompt del sistema</h2>

        {/* Provider / model status (read-only) */}
        <div className="rounded-lg border p-4 space-y-2 text-sm">
          <p className="font-medium">Estado del proveedor</p>
          {status ? (
            status.enabled ? (
              <div className="space-y-0.5 text-muted-foreground">
                <p>
                  <span className="font-medium text-foreground">
                    Proveedor:
                  </span>{" "}
                  {status.provider ?? "—"}
                </p>
                <p>
                  <span className="font-medium text-foreground">Modelo:</span>{" "}
                  {status.model ?? "—"}
                </p>
              </div>
            ) : (
              <p className="text-amber-600 dark:text-amber-400">
                No hay proveedor configurado. El chat no estará disponible para
                los usuarios hasta que se configure un proveedor LLM.
              </p>
            )
          ) : (
            <p className="text-muted-foreground">Cargando estado…</p>
          )}
        </div>

        {/* Last update metadata */}
        {prompt.updated_at ? (
          <p className="text-xs text-muted-foreground">
            Última modificación:{" "}
            {new Date(prompt.updated_at).toLocaleString("es-ES", {
              dateStyle: "medium",
              timeStyle: "short",
            })}
            {prompt.updated_by_email ? ` por ${prompt.updated_by_email}` : ""}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Sin cambios previos</p>
        )}

        {/* System prompt textarea */}
        <label className="block text-sm space-y-1">
          <span className="font-medium">System prompt</span>
          <textarea
            className={field}
            rows={8}
            maxLength={8000}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <span className="text-xs text-muted-foreground">
            {value.length} / 8000 caracteres
          </span>
        </label>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {saving ? "Guardando…" : "Guardar"}
          </button>

          <button
            type="button"
            onClick={handleRestore}
            className="rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground cursor-pointer"
          >
            Restaurar por defecto
          </button>
        </div>
      </section>
    </div>
  );
}
