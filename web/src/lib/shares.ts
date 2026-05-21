import { apiFetch } from "./api";

export interface UserSuggestion {
  id: string;
  email: string;
  display_name: string;
}

export const searchUsers = (q: string) =>
  apiFetch<UserSuggestion[]>(`/v1/users/search?q=${encodeURIComponent(q)}`);

export interface KBShare {
  id: string;
  kb_id: string;
  shared_with_id: string;
  shared_with_email: string;
  shared_with_display_name: string;
  access_level: "viewer" | "editor";
  created_at: string;
}

export const listShares = (kbId: string) =>
  apiFetch<KBShare[]>(`/v1/knowledge-bases/${kbId}/shares`);

export const createShare = (
  kbId: string,
  email: string,
  access_level: "viewer" | "editor",
) =>
  apiFetch<KBShare>(`/v1/knowledge-bases/${kbId}/shares`, {
    method: "POST",
    body: JSON.stringify({ email, access_level }),
  });

export const deleteShare = (kbId: string, shareId: string) =>
  apiFetch<void>(`/v1/knowledge-bases/${kbId}/shares/${shareId}`, {
    method: "DELETE",
  });
