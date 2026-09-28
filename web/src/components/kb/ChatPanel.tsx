"use client";

import * as React from "react";
import { X, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  getChatStatus,
  streamChat,
  type ChatMessage,
  type Citation,
  type ChatStatus,
} from "@/lib/chat";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AssistantMessage {
  role: "assistant";
  content: string;
  citations: Citation[];
}

interface UserMessage {
  role: "user";
  content: string;
}

type DisplayMessage = UserMessage | AssistantMessage;

// ─── Component ────────────────────────────────────────────────────────────────

export function ChatPanel({
  kbId,
  kbSlug,
  onClose,
}: {
  kbId: string;
  kbSlug: string;
  onClose: () => void;
}) {
  const [status, setStatus] = React.useState<ChatStatus | null>(null);
  const [statusError, setStatusError] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<DisplayMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  // Fetch chat status on mount.
  React.useEffect(() => {
    getChatStatus()
      .then(setStatus)
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "No se pudo obtener el estado del chat";
        setStatusError(msg);
      });
  }, []);

  // Scroll to bottom when messages change.
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const chatEnabled = status?.enabled === true;
  const isDisabled = !chatEnabled || streaming;

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isDisabled) return;

    // Build history from current messages (exclude the pending assistant message).
    const history: ChatMessage[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    // Add user message immediately.
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setStreaming(true);

    // Add placeholder for the assistant's response.
    const assistantIndex = messages.length + 1;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", citations: [] },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(kbId, text, history, {
        signal: controller.signal,
        onToken: (token) => {
          setMessages((prev) => {
            const next = [...prev];
            const msg = next[assistantIndex];
            if (msg?.role === "assistant") {
              next[assistantIndex] = { ...msg, content: msg.content + token };
            }
            return next;
          });
        },
        onSources: (sources) => {
          setMessages((prev) => {
            const next = [...prev];
            const msg = next[assistantIndex];
            if (msg?.role === "assistant") {
              next[assistantIndex] = { ...msg, citations: sources };
            }
            return next;
          });
        },
        onError: (message) => {
          toast.error(message);
          // Remove the empty assistant placeholder if nothing was written.
          setMessages((prev) => {
            const next = [...prev];
            const msg = next[assistantIndex];
            if (msg?.role === "assistant" && msg.content === "") {
              next.splice(assistantIndex, 1);
            }
            return next;
          });
        },
      });
    } catch (e) {
      if ((e as { name?: string }).name !== "AbortError") {
        toast.error(e instanceof Error ? e.message : "Error en el chat");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isLoading = status === null && statusError === null;

  return (
    <aside className="w-80 shrink-0 border-l border-border h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b shrink-0">
        <span className="text-sm font-semibold">Chat</span>
        <button
          onClick={onClose}
          aria-label="Cerrar panel de chat"
          className="p-1 rounded hover:bg-accent cursor-pointer"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Status banner when disabled */}
      {!isLoading && !chatEnabled && (
        <div className="px-3 py-2 border-b shrink-0">
          <p className="text-xs text-muted-foreground">
            {statusError ??
              "El chat no está disponible: no hay proveedor de LLM configurado"}
          </p>
        </div>
      )}

      {/* Loading indicator */}
      {isLoading && (
        <div className="flex items-center justify-center flex-1">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Messages list */}
      {!isLoading && (
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
          {messages.length === 0 && chatEnabled && (
            <p className="text-xs text-muted-foreground text-center pt-4">
              Pregunta algo sobre esta base de conocimiento.
            </p>
          )}

          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <UserBubble key={i} content={msg.content} />
            ) : (
              <AssistantBubble
                key={i}
                content={msg.content}
                citations={(msg as AssistantMessage).citations}
                kbSlug={kbSlug}
                isStreaming={streaming && i === messages.length - 1}
              />
            ),
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Input area */}
      <div className="shrink-0 border-t border-border p-2 flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={chatEnabled ? "Escribe un mensaje… (Enter para enviar)" : "Chat no disponible"}
          rows={2}
          disabled={isDisabled || isLoading}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm resize-none disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          onClick={handleSend}
          disabled={isDisabled || isLoading || !input.trim()}
          aria-label="Enviar mensaje"
          className="flex items-center justify-center p-2 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0"
        >
          {streaming ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
        </button>
      </div>
    </aside>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm whitespace-pre-wrap break-words">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({
  content,
  citations,
  kbSlug,
  isStreaming,
}: {
  content: string;
  citations: Citation[];
  kbSlug: string;
  isStreaming: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="max-w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap break-words">
        {content}
        {isStreaming && !content && (
          <span className="inline-block animate-pulse text-muted-foreground">▌</span>
        )}
      </div>

      {/* Citation chips */}
      {citations.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {citations.map((c) =>
            c.document_number !== null ? (
              <a
                key={c.n}
                href={`/wikis/${kbSlug}?p=${c.document_number}&cita=${encodeURIComponent(c.anchor_text)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
              >
                [{c.n}] {c.title ?? c.doc_path}
              </a>
            ) : (
              <a
                key={c.n}
                href={`/wikis/${kbSlug}?cita=${encodeURIComponent(c.anchor_text)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
              >
                [{c.n}] {c.title ?? c.doc_path}
              </a>
            ),
          )}
        </div>
      )}
    </div>
  );
}
