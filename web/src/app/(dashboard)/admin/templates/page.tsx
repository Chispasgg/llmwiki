"use client";

import { useEffect, useState } from "react";
import {
  listAllKBs,
  listLatexTemplates,
  assignKBLatexTemplate,
  type AdminKB,
} from "@/lib/admin";
import type { LatexTemplate } from "@/lib/types";

export default function AdminTemplatesPage() {
  const [kbs, setKbs] = useState<AdminKB[]>([]);
  const [templates, setTemplates] = useState<LatexTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listAllKBs(), listLatexTemplates()])
      .then(([kbList, tplList]) => {
        setKbs(kbList);
        setTemplates(tplList);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleAssign = async (kb: AdminKB, templateId: string | null) => {
    setSaving(kb.id);
    try {
      await assignKBLatexTemplate(kb.id, templateId);
      setKbs((prev) =>
        prev.map((k) =>
          k.id === kb.id
            ? {
                ...k,
                latex_template_id: templateId,
                latex_template_name:
                  templates.find((t) => t.id === templateId)?.display_name ??
                  null,
              }
            : k,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  };

  const filtered = kbs.filter(
    (kb) =>
      kb.name.toLowerCase().includes(search.toLowerCase()) ||
      kb.user_email.toLowerCase().includes(search.toLowerCase()),
  );

  if (loading) return <p className="text-muted-foreground">Cargando...</p>;

  return (
    <div>
      <h1 className="text-xl font-semibold mb-2">Templates PDF</h1>
      <p className="text-sm text-muted-foreground mb-6">
        Asigna una plantilla LaTeX a cada wiki. Si no hay asignación se usará la
        plantilla <span className="font-mono">default</span>.
      </p>

      {error && <p className="text-destructive mb-4">{error}</p>}

      <div className="mb-6">
        <h2 className="text-sm font-medium mb-2">Plantillas disponibles</h2>
        <div className="flex flex-wrap gap-2">
          {templates.map((t) => (
            <span
              key={t.id}
              className="text-xs bg-muted px-2 py-1 rounded font-mono"
              title={t.name}
            >
              {t.display_name}
            </span>
          ))}
          {templates.length === 0 && (
            <span className="text-xs text-muted-foreground">
              No hay plantillas registradas en la base de datos.
            </span>
          )}
        </div>
      </div>

      <input
        placeholder="Buscar por nombre o usuario..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-4 border rounded px-3 py-2 text-sm w-72"
      />

      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">Wiki</th>
            <th className="py-2 pr-4">Propietario</th>
            <th className="py-2">Plantilla asignada</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((kb) => (
            <tr key={kb.id} className="border-b hover:bg-muted/40">
              <td className="py-2 pr-4 font-medium">{kb.name}</td>
              <td className="py-2 pr-4 text-muted-foreground">
                {kb.user_email}
              </td>
              <td className="py-2">
                <select
                  value={kb.latex_template_id ?? ""}
                  disabled={saving === kb.id}
                  onChange={(e) => handleAssign(kb, e.target.value || null)}
                  className="border rounded px-2 py-1 text-sm bg-background disabled:opacity-50"
                >
                  <option value="">Default</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.display_name}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
