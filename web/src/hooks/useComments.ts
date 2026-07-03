import * as React from "react";
import { apiFetch } from "@/lib/api";
import type { WikiComment, CommentHistoryEntry } from "@/lib/types";

export function useComments(docId: string | null) {
  const [comments, setComments] = React.useState<WikiComment[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [showResolved, setShowResolved] = React.useState(false);

  const reload = React.useCallback(
    async (signal?: AbortSignal) => {
      if (!docId) {
        setComments([]);
        return;
      }
      setLoading(true);
      try {
        const status = showResolved ? "all" : "open";
        const data = await apiFetch<WikiComment[]>(
          `/v1/documents/${docId}/comments?status=${status}`,
          { signal },
        );
        setComments(data);
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          setComments([]);
        }
      } finally {
        setLoading(false);
      }
    },
    [docId, showResolved],
  );

  React.useEffect(() => {
    const ctrl = new AbortController();
    reload(ctrl.signal);
    return () => ctrl.abort();
  }, [reload]);

  const create = React.useCallback(
    async (body: string, targetText: string | null) => {
      if (!docId) throw new Error("No hay documento activo");
      await apiFetch(`/v1/documents/${docId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body, target_text: targetText }),
      });
      await reload();
    },
    [docId, reload],
  );

  const edit = React.useCallback(
    async (id: string, body: string) => {
      await apiFetch(`/v1/comments/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ body }),
      });
      await reload();
    },
    [reload],
  );

  const resolve = React.useCallback(
    async (id: string) => {
      await apiFetch(`/v1/comments/${id}/resolve`, { method: "POST" });
      await reload();
    },
    [reload],
  );

  const reopen = React.useCallback(
    async (id: string) => {
      await apiFetch(`/v1/comments/${id}/reopen`, { method: "POST" });
      await reload();
    },
    [reload],
  );

  const remove = React.useCallback(
    async (id: string) => {
      await apiFetch(`/v1/comments/${id}`, { method: "DELETE" });
      await reload();
    },
    [reload],
  );

  return {
    comments,
    loading,
    showResolved,
    setShowResolved,
    reload,
    create,
    edit,
    resolve,
    reopen,
    remove,
  };
}

export async function fetchCommentHistory(
  kbId: string,
): Promise<CommentHistoryEntry[]> {
  try {
    return await apiFetch<CommentHistoryEntry[]>(
      `/v1/knowledge-bases/${kbId}/comment-history`,
    );
  } catch {
    return [];
  }
}
