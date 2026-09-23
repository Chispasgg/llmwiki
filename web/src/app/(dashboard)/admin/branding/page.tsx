"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  getBranding,
  putBranding,
  resetBranding,
  type BrandingAdmin,
} from "@/lib/admin";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { invalidateBrandingCache } from "@/hooks/useBranding";

const ALLOWED_MIME = new Set([
  "image/svg+xml",
  "image/png",
  "image/jpeg",
  "image/webp",
]);
const MAX_BYTES = 512 * 1024;

const field =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

export default function AdminBrandingPage() {
  const [branding, setBranding] = useState<BrandingAdmin | null>(null);

  // Form state
  const [orgName, setOrgName] = useState("");
  const [previewUri, setPreviewUri] = useState<string | null>(null);
  const [previewMime, setPreviewMime] = useState<string | null>(null);

  // Button states
  const [saving, setSaving] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = () => {
    getBranding()
      .then((data) => {
        setBranding(data);
        setOrgName(data.org_name ?? "");
        // Clear file preview when reloading from server
        setPreviewUri(null);
        setPreviewMime(null);
      })
      .catch(() => toast.error("No se pudo cargar la configuración de marca"));
  };

  useEffect(() => {
    load();
    return () => {
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ALLOWED_MIME.has(file.type)) {
      toast.error("Tipo de archivo no permitido. Usa SVG, PNG, JPEG o WebP.");
      e.target.value = "";
      return;
    }

    if (file.size > MAX_BYTES) {
      toast.error("El archivo supera el límite de 512 KB.");
      e.target.value = "";
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      setPreviewUri(reader.result as string);
      setPreviewMime(file.type);
    };
    reader.readAsDataURL(file);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // If the user didn't pick a new file, keep the existing logo from server
      const logo_data_uri = previewUri ?? branding?.logo ?? null;
      const logo_mime = previewMime ?? branding?.logo_mime ?? null;

      const updated = await putBranding({
        org_name: orgName.trim() || null,
        logo_data_uri,
        logo_mime,
      });

      setBranding(updated);
      setOrgName(updated.org_name ?? "");
      setPreviewUri(null);
      setPreviewMime(null);
      invalidateBrandingCache();
      toast.success("Configuración de marca guardada");
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Error al guardar la marca";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!resetConfirm) {
      setResetConfirm(true);
      resetTimerRef.current = setTimeout(() => setResetConfirm(false), 4000);
      return;
    }
    setResetConfirm(false);
    try {
      const updated = await resetBranding();
      setBranding(updated);
      setOrgName("");
      setPreviewUri(null);
      setPreviewMime(null);
      invalidateBrandingCache();
      toast.success("Marca restaurada a los valores por defecto");
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Error al restaurar la marca";
      toast.error(msg);
    }
  };

  // The logo shown in previews: prefer the newly selected file, then the
  // saved server value.
  const displayLogo = previewUri ?? branding?.logo ?? null;

  if (!branding) {
    return <p className="text-sm text-muted-foreground">Cargando…</p>;
  }

  return (
    <div className="max-w-lg space-y-6">
      <h1 className="text-xl font-bold">Marca (Branding)</h1>

      {/* Current state summary */}
      <div className="flex items-center gap-4 rounded-lg border p-4">
        <BrandLogo logo={displayLogo} size={48} rounded />
        <div className="text-sm space-y-0.5">
          <p className="font-medium">
            {branding.org_name ?? <span className="text-muted-foreground">Sin nombre — se muestra «LLM Wiki»</span>}
          </p>
          {branding.updated_at ? (
            <p className="text-muted-foreground">
              Actualizado el{" "}
              {new Date(branding.updated_at).toLocaleString("es-ES", {
                dateStyle: "medium",
                timeStyle: "short",
              })}
              {branding.updated_by_email ? ` por ${branding.updated_by_email}` : ""}
            </p>
          ) : (
            <p className="text-muted-foreground">Sin cambios previos</p>
          )}
        </div>
      </div>

      {/* Org name */}
      <label className="block text-sm space-y-1">
        <span className="font-medium">Nombre de organización</span>
        <input
          className={field}
          value={orgName}
          maxLength={60}
          placeholder="Mi empresa"
          onChange={(e) => setOrgName(e.target.value)}
        />
        <span className="text-xs text-muted-foreground">
          La pestaña mostrará «{orgName.trim() || "LLM"} Wiki». Vacío = LLM Wiki.
        </span>
      </label>

      {/* Logo upload */}
      <div className="space-y-2">
        <p className="text-sm font-medium">Logo</p>
        <input
          type="file"
          accept="image/svg+xml,image/png,image/jpeg,image/webp"
          className="text-sm"
          onChange={handleFileChange}
        />
        <p className="text-xs text-muted-foreground">
          SVG, PNG, JPEG o WebP · máx. 512 KB
        </p>
        {previewUri && (
          <div className="flex items-center gap-3 rounded-md border p-3">
            <BrandLogo logo={previewUri} size={48} rounded />
            <span className="text-xs text-muted-foreground">Previsualización</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
        >
          {saving ? "Guardando…" : "Guardar"}
        </button>

        <button
          onClick={handleReset}
          className={
            resetConfirm
              ? "rounded-lg border border-destructive px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 cursor-pointer"
              : "rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground cursor-pointer"
          }
        >
          {resetConfirm ? "¿Restaurar por defecto? Haz clic de nuevo" : "Restaurar por defecto"}
        </button>
      </div>
    </div>
  );
}
