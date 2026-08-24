"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import { searchWikis, type SearchHit } from "@/lib/search";

function stripTags(html: string): string {
  return html.replace(/<\/?[^>]+>/g, "");
}

function docTitle(hit: SearchHit): string {
  if (hit.title) return hit.title;
  // Extrae el basename del doc_path
  const parts = hit.doc_path.split("/");
  return parts[parts.length - 1] ?? hit.doc_path;
}

function buildHref(hit: SearchHit): string {
  const rel = hit.doc_path.replace(/^\/wiki\/?/, "");
  return hit.document_number != null
    ? `/wikis/${hit.kb_slug}?p=${hit.document_number}`
    : `/wikis/${hit.kb_slug}?page=${encodeURIComponent(rel)}`;
}

export function GlobalWikiSearch() {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<SearchHit[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [searched, setSearched] = React.useState(false);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function handleChange(val: string) {
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (val.length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setSearched(false);
      try {
        const hits = await searchWikis(val);
        setResults(hits);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
        setSearched(true);
      }
    }, 300);
  }

  const showEmpty = searched && !loading && results.length === 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
        <input
          type="search"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Buscar en todos los wikis..."
          className="w-full rounded-lg border border-input bg-background pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {loading && (
        <div className="flex justify-center py-4">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      )}

      {showEmpty && (
        <p className="text-xs text-muted-foreground text-center py-3">
          Sin resultados para &ldquo;{query}&rdquo;
        </p>
      )}

      {!loading && results.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {results.map((hit, i) => (
            <li key={i}>
              <button
                onClick={() => router.push(buildHref(hit))}
                className="w-full text-left rounded-lg border border-border bg-card hover:bg-accent/40 transition-colors px-3 py-2.5 flex flex-col gap-1 cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[10px] font-medium shrink-0">
                    {hit.kb_name}
                  </span>
                  <span className="text-sm font-medium text-foreground truncate">
                    {docTitle(hit)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {stripTags(hit.snippet)}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
