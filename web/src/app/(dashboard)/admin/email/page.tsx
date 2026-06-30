"use client";

import * as React from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";

type SmtpSettings = {
  host: string;
  port: number;
  username: string;
  from_address: string;
  use_tls: boolean;
  enabled: boolean;
  digest_interval_minutes: number;
  password_set: boolean;
};

export default function AdminEmailPage() {
  const [s, setS] = React.useState<SmtpSettings | null>(null);
  const [password, setPassword] = React.useState("");
  const [testTo, setTestTo] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);

  React.useEffect(() => {
    apiFetch<SmtpSettings>("/v1/superadmin/smtp")
      .then(setS)
      .catch(() => toast.error("No se pudo cargar la configuración SMTP"));
  }, []);

  if (!s) return <p className="text-sm text-muted-foreground">Cargando…</p>;

  const update = (patch: Partial<SmtpSettings>) => setS({ ...s, ...patch });

  const body = () => ({
    host: s.host,
    port: Number(s.port),
    username: s.username,
    from_address: s.from_address,
    use_tls: s.use_tls,
    enabled: s.enabled,
    digest_interval_minutes: Number(s.digest_interval_minutes),
    password: password || null,
  });

  const save = async () => {
    setSaving(true);
    try {
      const updated = await apiFetch<SmtpSettings>("/v1/superadmin/smtp", {
        method: "PUT",
        body: JSON.stringify(body()),
      });
      setS(updated);
      setPassword("");
      toast.success("Configuración SMTP guardada");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    if (!testTo) return;
    setTesting(true);
    try {
      await apiFetch("/v1/superadmin/smtp/test", {
        method: "POST",
        body: JSON.stringify({ ...body(), to: testTo }),
      });
      toast.success(`Correo de prueba enviado a ${testTo}`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Fallo al enviar la prueba",
      );
    } finally {
      setTesting(false);
    }
  };

  const field =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm";

  return (
    <div className="max-w-lg space-y-4">
      <h1 className="text-xl font-bold">Configuración de email (SMTP)</h1>

      <label className="block text-sm">
        Host
        <input
          className={field}
          value={s.host}
          onChange={(e) => update({ host: e.target.value })}
        />
      </label>
      <label className="block text-sm">
        Puerto
        <input
          className={field}
          type="number"
          value={s.port}
          onChange={(e) => update({ port: Number(e.target.value) })}
        />
      </label>
      <label className="block text-sm">
        Usuario
        <input
          className={field}
          value={s.username}
          onChange={(e) => update({ username: e.target.value })}
        />
      </label>
      <label className="block text-sm">
        Contraseña
        <input
          className={field}
          type="password"
          placeholder={s.password_set ? "•••••• (sin cambios)" : ""}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label className="block text-sm">
        Remitente (From)
        <input
          className={field}
          value={s.from_address}
          onChange={(e) => update({ from_address: e.target.value })}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={s.use_tls}
          onChange={(e) => update({ use_tls: e.target.checked })}
        />
        Usar TLS (STARTTLS)
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={s.enabled}
          onChange={(e) => update({ enabled: e.target.checked })}
        />
        Envío de emails activado
      </label>
      <label className="block text-sm">
        Intervalo del digest (minutos, mínimo 5)
        <input
          className={field}
          type="number"
          min={5}
          value={s.digest_interval_minutes}
          onChange={(e) =>
            update({ digest_interval_minutes: Number(e.target.value) })
          }
        />
      </label>

      <button
        onClick={save}
        disabled={saving}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
      >
        {saving ? "Guardando…" : "Guardar"}
      </button>

      <div className="border-t pt-4 space-y-2">
        <h2 className="text-sm font-semibold">Enviar correo de prueba</h2>
        <div className="flex gap-2">
          <input
            className={field}
            placeholder="destino@ejemplo.com"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
          />
          <button
            onClick={sendTest}
            disabled={testing || !testTo}
            className="shrink-0 rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50 cursor-pointer"
          >
            {testing ? "Enviando…" : "Enviar prueba"}
          </button>
        </div>
      </div>
    </div>
  );
}
