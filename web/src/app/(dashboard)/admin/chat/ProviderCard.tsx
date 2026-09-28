"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  putAiProvider,
  getProviderModels,
  type AiProvider,
  type AiProvidersResponse,
} from "@/lib/admin";

const field =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
};

interface Props {
  provider: AiProvider;
  isActive: boolean;
  onSaved: (updated: AiProvidersResponse) => void;
}

export function ProviderCard({ provider, isActive, onSaved }: Props) {
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [apiKey, setApiKey] = useState(""); // empty = don't change
  const [model, setModel] = useState(provider.model);
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelsFetched, setModelsFetched] = useState(false);
  const [saving, setSaving] = useState(false);

  const isOllama = provider.provider === "ollama";
  const label = PROVIDER_LABELS[provider.provider] ?? provider.provider;

  const handleFetchModels = async () => {
    setLoadingModels(true);
    setModelsError(null);
    try {
      const data = await getProviderModels(provider.provider);
      setModels(data.models);
      setModelsError(data.error ?? null);
      setModelsFetched(true);
      // Pre-select first model if current model is not in the list
      if (data.models.length > 0 && !data.models.includes(model)) {
        setModel(data.models[0]);
      }
    } catch {
      setModelsError("No se pudo conectar con el servidor de modelos");
      setModels([]);
      setModelsFetched(true);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const body: { base_url?: string; api_key?: string; model?: string } = {
        base_url: baseUrl,
        model,
      };
      // Only send api_key if the user actually typed something (and not Ollama)
      if (!isOllama && apiKey.trim()) {
        body.api_key = apiKey.trim();
      }
      const updated = await putAiProvider(provider.provider, body);
      onSaved(updated);
      // Sync local state from server response
      const updatedProvider = updated.providers.find(
        (p) => p.provider === provider.provider,
      );
      if (updatedProvider) {
        setBaseUrl(updatedProvider.base_url);
        setModel(updatedProvider.model);
      }
      setApiKey("");
      toast.success(`Proveedor ${label} guardado`);
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : `Error al guardar ${label}`;
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const showModelSelect =
    modelsFetched && models.length > 0 && modelsError === null;
  const showModelFallback =
    !modelsFetched || models.length === 0 || modelsError !== null;

  return (
    <div
      className={`rounded-lg border p-4 space-y-4 transition-colors ${
        isActive ? "border-primary bg-primary/5" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <p className="font-medium text-sm capitalize">{label}</p>
        {isActive && (
          <span className="text-xs font-medium rounded-full bg-primary text-primary-foreground px-2 py-0.5">
            Activo
          </span>
        )}
      </div>

      {/* Base URL */}
      <label className="block text-sm space-y-1">
        <span className="font-medium">URL base</span>
        <input
          className={field}
          value={baseUrl}
          placeholder="http://localhost:11434"
          onChange={(e) => setBaseUrl(e.target.value)}
        />
      </label>

      {/* API Key — hidden for Ollama (no auth required) */}
      {!isOllama && (
        <label className="block text-sm space-y-1">
          <span className="font-medium">API Key</span>
          <input
            type="password"
            className={field}
            value={apiKey}
            placeholder={
              provider.has_api_key
                ? "•••• (definida — vacío = no cambiar)"
                : "Sin clave definida"
            }
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
      )}

      {/* Model */}
      <div className="text-sm space-y-1">
        <div className="flex items-center justify-between">
          <span className="font-medium">Modelo</span>
          <button
            type="button"
            onClick={handleFetchModels}
            disabled={loadingModels}
            className="text-xs text-primary hover:underline disabled:opacity-50 cursor-pointer"
          >
            {loadingModels ? "Cargando…" : "Refrescar modelos"}
          </button>
        </div>

        {showModelSelect && (
          <select
            className={field}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}

        {showModelFallback && (
          <>
            <input
              className={field}
              value={model}
              placeholder="Nombre del modelo (ej. llama3)"
              onChange={(e) => setModel(e.target.value)}
            />
            {modelsFetched && modelsError && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                {modelsError} — escribe el modelo manualmente.
              </p>
            )}
            {modelsFetched && !modelsError && models.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No se encontraron modelos — escribe el nombre manualmente.
              </p>
            )}
          </>
        )}
      </div>

      {/* Save */}
      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
      >
        {saving ? "Guardando…" : "Guardar"}
      </button>
    </div>
  );
}
