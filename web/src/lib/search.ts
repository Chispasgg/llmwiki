import { apiFetch } from "./api";

export interface SearchHit {
  kb_name: string;
  kb_slug: string;
  doc_path: string;
  title: string | null;
  snippet: string;
  score: number;
  document_number: number | null;
}

export const searchWikis = (q: string) =>
  apiFetch<SearchHit[]>(`/v1/search?q=${encodeURIComponent(q)}`);
