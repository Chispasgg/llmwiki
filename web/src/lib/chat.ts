import { apiFetch, API_URL, API_CREDENTIALS } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Citation {
  n: number;
  title: string | null;
  doc_path: string;
  document_number: number | null;
  anchor_text: string;
}

export interface ChatStatus {
  enabled: boolean;
  provider: string;
  model: string;
}

// ─── API calls ────────────────────────────────────────────────────────────────

export function getChatStatus(): Promise<ChatStatus> {
  return apiFetch<ChatStatus>("/v1/chat/status");
}

export interface StreamChatHandlers {
  onToken: (text: string) => void;
  onSources: (sources: Citation[]) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/**
 * Streams a chat response from the backend.
 *
 * Handles two cases:
 * 1. JSON response with `{ enabled: false }` → calls onError.
 * 2. SSE stream (`text/event-stream`) → dispatches tokens, sources, and errors.
 *
 * Manages partial-chunk buffering so lines split across chunks are reassembled.
 */
export async function streamChat(
  kbId: string,
  message: string,
  history: ChatMessage[],
  { onToken, onSources, onError, signal }: StreamChatHandlers,
): Promise<void> {
  const res = await fetch(
    `${API_URL}/v1/knowledge-bases/${kbId}/chat`,
    {
      method: "POST",
      credentials: API_CREDENTIALS,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal,
    },
  );

  if (!res.ok) {
    let msg = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {
      // ignore parse error
    }
    onError(msg);
    return;
  }

  const contentType = res.headers.get("content-type") ?? "";

  // Backend indicates chat is disabled.
  if (contentType.includes("application/json")) {
    try {
      const body = (await res.json()) as { enabled?: boolean };
      if (body.enabled === false) {
        onError("El chat no está disponible: no hay proveedor de LLM configurado");
        return;
      }
    } catch {
      onError("Respuesta inesperada del servidor");
    }
    return;
  }

  // SSE stream
  if (!res.body) {
    onError("Sin cuerpo de respuesta");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Split on double newline (SSE event boundary) but keep remainder.
      const lines = buffer.split("\n");
      // All lines except the last are complete; the last may be partial.
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const raw = trimmed.slice(5).trim();
        if (!raw || raw === "[DONE]") continue;

        let event: { type: string; text?: string; sources?: Citation[]; message?: string };
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }

        if (event.type === "token" && typeof event.text === "string") {
          onToken(event.text);
        } else if (event.type === "sources" && Array.isArray(event.sources)) {
          onSources(event.sources as Citation[]);
        } else if (event.type === "error" && typeof event.message === "string") {
          onError(event.message);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
