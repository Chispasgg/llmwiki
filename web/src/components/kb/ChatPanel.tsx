"use client";

import * as React from "react";
import { X, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import {
  getChatStatus,
  streamChat,
  type ChatMessage,
  type Citation,
  type ChatStatus,
} from "@/lib/chat";

// ─── Constants ────────────────────────────────────────────────────────────────

const CHAT_MIN = 320;
const CHAT_MAX = 720;
const CHAT_DEFAULT = 320;
const CHAT_STORAGE_KEY = "wiki_chat_width";

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

// ─── Markdown components ──────────────────────────────────────────────────────

const mdComponents: Components = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  h1: ({ children }) => (
    <h1 className="text-base font-bold mt-3 mb-1 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-bold mt-2.5 mb-1 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold mt-2 mb-0.5 first:mt-0">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => (
    <ul className="list-disc pl-4 mb-1.5 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-4 mb-1.5 space-y-0.5">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border pl-3 italic text-muted-foreground my-1.5">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.startsWith("language-");
    if (isBlock) {
      return (
        <code className="block w-full font-mono text-[12px] leading-relaxed">
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-muted px-1 py-0.5 font-mono text-[12px]">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="rounded-md border border-border bg-muted p-2.5 overflow-x-auto text-[12px] my-1.5">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-1.5">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border px-2 py-1 text-left font-semibold bg-muted">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border px-2 py-1">{children}</td>
  ),
  hr: () => <hr className="border-border my-2" />,
};

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

  // ─── Panel width (resizable) ────────────────────────────────────────────────
  const [chatWidth, setChatWidth] = React.useState(CHAT_DEFAULT);
  const dragWidthRef = React.useRef(CHAT_DEFAULT);

  React.useEffect(() => {
    try {
      const stored = localStorage.getItem(CHAT_STORAGE_KEY);
      if (stored) {
        const n = parseInt(stored, 10);
        if (n >= CHAT_MIN && n <= CHAT_MAX) {
          setChatWidth(n);
          dragWidthRef.current = n;
        }
      }
    } catch {
      // localStorage unavailable — use default
    }
  }, []);

  const handleResizeMouseDown = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = dragWidthRef.current;

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMouseMove = (ev: MouseEvent) => {
        // Drag handle is on the LEFT of the panel: moving left → wider
        const newWidth = Math.min(
          CHAT_MAX,
          Math.max(CHAT_MIN, startWidth + (startX - ev.clientX)),
        );
        dragWidthRef.current = newWidth;
        setChatWidth(newWidth);
      };

      const onMouseUp = () => {
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        try {
          localStorage.setItem(CHAT_STORAGE_KEY, String(dragWidthRef.current));
        } catch {
          // ignore
        }
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };

      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [],
  );

  // Fetch chat status on mount.
  React.useEffect(() => {
    getChatStatus()
      .then(setStatus)
      .catch((e) => {
        const msg =
          e instanceof Error
            ? e.message
            : "No se pudo obtener el estado del chat";
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
    <aside
      style={{ width: chatWidth }}
      className="shrink-0 border-l border-border h-full flex flex-row bg-background"
    >
      {/* Resize handle — left edge of the panel */}
      <div
        onMouseDown={handleResizeMouseDown}
        className="shrink-0 w-1 cursor-col-resize flex items-stretch group z-10"
      >
        <div className="w-px bg-border group-hover:bg-primary/40 transition-colors duration-150 mx-auto" />
      </div>

      {/* Panel content */}
      <div className="flex-1 flex flex-col min-w-0">
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
            placeholder={
              chatEnabled
                ? "Escribe un mensaje… (Enter para enviar)"
                : "Chat no disponible"
            }
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
      <div className="max-w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm break-words overflow-hidden">
        {content ? (
          <>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={mdComponents}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block animate-pulse text-muted-foreground">
                ▌
              </span>
            )}
          </>
        ) : (
          isStreaming && (
            <span className="inline-block animate-pulse text-muted-foreground">
              ▌
            </span>
          )
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
