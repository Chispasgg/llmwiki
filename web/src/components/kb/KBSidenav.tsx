"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight,
  FileText,
  NotepadText,
  Library,
  Upload,
  BookOpen,
  ArrowUpRight,
  Search as SearchIcon,
  Lightbulb,
  Box,
  ScrollText,
  Network,
  Folder,
  Users2,
  FileDown,
  MoreHorizontal,
} from "lucide-react";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandItem,
  CommandEmpty,
  CommandGroup,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { WikiSelector } from "@/components/kb/WikiSelector";
import { SidenavUserMenu } from "@/components/kb/SidenavUserMenu";
import { ShareDialog } from "@/components/kb/ShareDialog";
import { WikiPageContextMenu } from "@/components/kb/ContextMenus";
import { ExportPdfDialog } from "@/components/kb/ExportPdfDialog";
import { apiFetch, API_URL, API_CREDENTIALS } from "@/lib/api";
import { useKBStore, useUserStore } from "@/stores";
import type { DocumentListItem, WikiNode } from "@/lib/types";

interface Usage {
  total_pages: number;
  total_storage_bytes: number;
  document_count: number;
  max_pages: number;
  max_storage_bytes: number;
}

function SpacePickerModal({
  open,
  onClose,
  currentSpaceId,
  title,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  currentSpaceId: string;
  title: string;
  onConfirm: (spaceId: string) => void;
}) {
  const knowledgeBases = useKBStore((s) => s.knowledgeBases);
  const [selected, setSelected] = React.useState<string | null>(null);
  const choices = knowledgeBases.filter((kb) => kb.id !== currentSpaceId);

  React.useEffect(() => {
    if (!open) setSelected(null);
  }, [open]);

  if (!open) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {choices.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No other spaces available
            </p>
          ) : (
            choices.map((kb) => (
              <button
                key={kb.id}
                onClick={() => setSelected(kb.id)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                  selected === kb.id
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-accent",
                )}
              >
                {kb.name}
              </button>
            ))
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent cursor-pointer"
          >
            Cancel
          </button>
          <button
            disabled={!selected}
            onClick={() => {
              if (selected) {
                onConfirm(selected);
                onClose();
              }
            }}
            className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            Confirm
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface KBSidenavProps {
  kbId: string;
  kbName: string;
  wikiTree: WikiNode[];
  wikiActivePath: string | null;
  onWikiNavigate: (
    path: string,
    docNumber?: number | null,
    searchTerm?: string,
  ) => void;
  sourceDocs: DocumentListItem[];
  hasWiki: boolean;
  loading: boolean;
  onUpload: () => void;
  filesViewActive: boolean;
  onFilesToggle: () => void;
  graphViewActive: boolean;
  onGraphToggle: () => void;
  onOpenSourceDoc: (docId: string) => void;
  onClose?: () => void;
  onMoveToSpace?: (docId: string, targetSpaceId: string) => void;
  onCopyToSpace?: (docId: string, targetSpaceId: string) => void;
  workspaceSlug?: string | null;
}

export function KBSidenav({
  kbId,
  kbName,
  wikiTree,
  wikiActivePath,
  onWikiNavigate,
  sourceDocs,
  hasWiki,
  loading,
  onUpload,
  filesViewActive,
  onFilesToggle,
  graphViewActive,
  onGraphToggle,
  onOpenSourceDoc,
  onClose,
  onMoveToSpace,
  onCopyToSpace,
  workspaceSlug,
}: KBSidenavProps) {
  const router = useRouter();
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [commandQuery, setCommandQuery] = React.useState("");
  const [shareOpen, setShareOpen] = React.useState(false);
  const [exportDialogOpen, setExportDialogOpen] = React.useState(false);
  const [exportLoading, setExportLoading] = React.useState(false);
  const [actionsOpen, setActionsOpen] = React.useState(false);
  const actionsRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!actionsOpen) return;
    const handler = (e: MouseEvent) => {
      if (
        actionsRef.current &&
        !actionsRef.current.contains(e.target as Node)
      ) {
        setActionsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [actionsOpen]);
  const currentUser = useUserStore((s) => s.user);
  const kb = useKBStore((s) => s.knowledgeBases.find((k) => k.id === kbId));
  const isOwner = !!currentUser && !!kb && kb.user_id === currentUser.id;
  const isSuperadmin = currentUser?.role === "superadmin";

  const handleExport = async (
    docIds: string[],
    format: "pdf" | "docx" | "odt",
    texFile?: File,
  ) => {
    setExportLoading(true);
    try {
      let body: BodyInit;
      const headers: Record<string, string> = {};

      if (format === "pdf") {
        const form = new FormData();
        form.append("doc_ids", JSON.stringify(docIds));
        if (texFile) form.append("tex_template", texFile);
        body = form;
      } else {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify({ doc_ids: docIds });
      }

      const response = await fetch(
        `${API_URL}/v1/knowledge-bases/${kbId}/export.${format}`,
        {
          method: "POST",
          credentials: API_CREDENTIALS,
          headers,
          body,
        },
      );
      if (!response.ok) {
        let msg = `Error al generar el ${format.toUpperCase()}`;
        try {
          const err = (await response.json()) as {
            detail?: string | { error?: string };
          };
          if (
            err?.detail &&
            typeof err.detail === "object" &&
            err.detail.error
          ) {
            msg = err.detail.error;
          } else if (typeof err?.detail === "string") {
            msg = err.detail;
          }
        } catch (_e) {}
        toast.error(msg);
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${kbName || "wiki"}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 150);
      setExportDialogOpen(false);
    } catch (err) {
      console.error("[Export]", err);
      toast.error(`Error al generar el ${format.toUpperCase()}`);
    } finally {
      setExportLoading(false);
    }
  };

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isMac = React.useMemo(
    () =>
      typeof navigator !== "undefined" &&
      /Mac|iPod|iPhone|iPad/.test(navigator.userAgent),
    [],
  );

  const allSearchableItems = React.useMemo(() => {
    const items: {
      type: "wiki" | "source";
      title: string;
      keywords: string;
      tags: string[];
      path?: string;
      docNumber?: number | null;
      doc?: DocumentListItem;
      spaceName?: string;
    }[] = [];
    const addWikiNodes = (nodes: WikiNode[], parentPath = "") => {
      for (const node of nodes) {
        if (node.path) {
          const matchingDoc = sourceDocs.find(
            (d) =>
              d.path === "/wiki/" && d.filename === node.path?.split("/").pop(),
          );
          const tags = matchingDoc?.tags ?? [];
          items.push({
            type: "wiki",
            title: node.title,
            keywords: [node.title, node.path, parentPath, ...tags]
              .filter(Boolean)
              .join(" "),
            tags,
            path: node.path,
            docNumber: node.docNumber,
          });
        }
        if (node.children) addWikiNodes(node.children, node.title);
      }
    };
    addWikiNodes(wikiTree);
    for (const doc of sourceDocs) {
      const tags = doc.tags ?? [];
      items.push({
        type: "source",
        title: doc.title || doc.filename,
        keywords: [doc.title, doc.filename, doc.path, doc.file_type, ...tags]
          .filter(Boolean)
          .join(" "),
        tags,
        doc,
      });
    }
    return items;
  }, [wikiTree, sourceDocs]);

  const sourceCount = sourceDocs.length;

  return (
    <div className="h-full flex flex-col border-r border-border">
      {/* Wiki selector */}
      <div className="shrink-0 px-2 pt-2 pb-1">
        <WikiSelector kbId={kbId} kbName={kbName} />
      </div>

      {/* Search + Actions menu */}
      <div className="shrink-0 px-2 pb-1 flex items-center gap-1.5">
        <button
          onClick={() => setSearchOpen(true)}
          aria-label="Search pages and sources"
          className="flex items-center gap-2 flex-1 px-2.5 py-1.5 text-xs text-muted-foreground/50 hover:text-muted-foreground border border-border hover:bg-accent rounded-md transition-colors cursor-pointer"
        >
          <SearchIcon className="size-3" />
          <span className="flex-1 text-left">Search</span>
          <kbd className="text-[10px] text-muted-foreground/30 bg-muted px-1 rounded">
            {isMac ? "⌘K" : "Ctrl+K"}
          </kbd>
        </button>
        <div className="relative" ref={actionsRef}>
          <button
            onClick={() => setActionsOpen((prev) => !prev)}
            aria-label="Acciones"
            title="Acciones"
            className={cn(
              "flex items-center justify-center px-2.5 py-1.5 border rounded-md transition-colors cursor-pointer",
              actionsOpen
                ? "bg-accent text-foreground border-border"
                : "text-muted-foreground/50 hover:text-muted-foreground border-border hover:bg-accent",
            )}
          >
            <MoreHorizontal className="size-3" />
          </button>
          {actionsOpen && (
            <div className="absolute right-0 top-full mt-1 z-50 min-w-[168px] rounded-md border border-border bg-popover shadow-md py-1">
              <button
                onClick={() => {
                  onGraphToggle();
                  setActionsOpen(false);
                }}
                className={cn(
                  "flex items-center gap-2.5 w-full px-3 py-1.5 text-xs transition-colors cursor-pointer",
                  graphViewActive
                    ? "text-foreground bg-accent"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent",
                )}
              >
                <Network className="size-3.5 shrink-0" />
                Knowledge graph
              </button>
              <button
                onClick={() => {
                  onUpload();
                  setActionsOpen(false);
                }}
                className="flex items-center gap-2.5 w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
              >
                <Upload className="size-3.5 shrink-0" />
                Subir archivos
              </button>
              {isOwner && (
                <button
                  onClick={() => {
                    setShareOpen(true);
                    setActionsOpen(false);
                  }}
                  className="flex items-center gap-2.5 w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
                >
                  <Users2 className="size-3.5 shrink-0" />
                  Compartir wiki
                </button>
              )}
              <div className="my-1 border-t border-border" />
              <button
                onClick={() => {
                  setExportDialogOpen(true);
                  setActionsOpen(false);
                }}
                className="flex items-center gap-2.5 w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
              >
                <FileDown className="size-3.5 shrink-0" />
                Exportar wiki
              </button>
            </div>
          )}
        </div>
      </div>

      {isOwner && (
        <ShareDialog
          kbId={kbId}
          kbName={kbName}
          open={shareOpen}
          onOpenChange={setShareOpen}
        />
      )}

      <ExportPdfDialog
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        kbName={kbName}
        wikiTree={wikiTree}
        onExport={handleExport}
        loading={exportLoading}
        isSuperadmin={isSuperadmin}
      />

      {/* Search palette */}
      <CommandDialog
        open={searchOpen}
        onOpenChange={(open) => {
          setSearchOpen(open);
          if (!open) setCommandQuery("");
        }}
      >
        <CommandInput
          value={commandQuery}
          onValueChange={setCommandQuery}
          placeholder="Jump to page, source, or action..."
          aria-label="Search pages and sources"
        />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          {allSearchableItems.some((i) => i.type === "wiki") && (
            <CommandGroup heading="Wiki">
              {allSearchableItems
                .filter((i) => i.type === "wiki")
                .map((item) => (
                  <CommandItem
                    key={`wiki-${item.path}`}
                    value={item.keywords}
                    onSelect={() => {
                      const query = commandQuery;
                      setSearchOpen(false);
                      setCommandQuery("");
                      if (item.path)
                        onWikiNavigate(item.path, item.docNumber, query);
                    }}
                    className="flex items-center"
                  >
                    <FileText className="size-3.5 mr-2 opacity-50 shrink-0" />
                    <span className="truncate flex-1 min-w-0">
                      {item.title}
                    </span>
                    <span className="ml-auto flex items-center gap-1 shrink-0 pl-2">
                      {item.spaceName && (
                        <span className="text-[10px] text-muted-foreground/50 bg-muted px-1.5 py-0.5 rounded">
                          {item.spaceName}
                        </span>
                      )}
                      {item.tags.slice(0, 2).map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] text-muted-foreground/50 bg-muted px-1.5 py-0.5 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </CommandItem>
                ))}
            </CommandGroup>
          )}
          {allSearchableItems.some((i) => i.type === "source") && (
            <CommandGroup heading="Sources">
              {allSearchableItems
                .filter((i) => i.type === "source")
                .map((item) => (
                  <CommandItem
                    key={`source-${item.doc?.id}`}
                    value={item.keywords}
                    onSelect={() => {
                      setSearchOpen(false);
                      if (item.doc) onOpenSourceDoc(item.doc.id);
                    }}
                    className="flex items-center"
                  >
                    <NotepadText className="size-3.5 mr-2 opacity-50 shrink-0" />
                    <span className="truncate flex-1 min-w-0">
                      {item.title}
                    </span>
                    <span className="ml-auto flex items-center gap-1 shrink-0 pl-2">
                      {item.spaceName && (
                        <span className="text-[10px] text-muted-foreground/50 bg-muted px-1.5 py-0.5 rounded">
                          {item.spaceName}
                        </span>
                      )}
                      {item.tags.slice(0, 2).map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] text-muted-foreground/50 bg-muted px-1.5 py-0.5 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </span>
                  </CommandItem>
                ))}
            </CommandGroup>
          )}
          <CommandSeparator />
          <CommandGroup heading="Actions">
            <CommandItem
              onSelect={() => {
                setSearchOpen(false);
                onFilesToggle();
              }}
            >
              <Folder className="size-3.5 mr-2 opacity-50" />
              Browse Files
            </CommandItem>
            <CommandItem
              onSelect={() => {
                setSearchOpen(false);
                onUpload();
              }}
            >
              <Upload className="size-3.5 mr-2 opacity-50" />
              Upload Files
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>

      {/* Wiki tree */}
      <div className="flex-1 min-h-0 flex flex-col px-2 pt-1">
        <div className="flex items-center px-2 mb-1 shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/50">
            Wiki
          </span>
        </div>
        {loading ? (
          <SidenavSkeleton lines={3} />
        ) : hasWiki ? (
          <div className="flex-1 overflow-y-auto no-scrollbar">
            {wikiTree.map((node, i) => (
              <WikiTreeNode
                key={node.path ?? node.title ?? i}
                node={node}
                depth={0}
                activePath={wikiActivePath}
                onNavigate={onWikiNavigate}
                onClose={onClose}
                kbId={kbId}
                onMoveToSpace={onMoveToSpace}
                onCopyToSpace={onCopyToSpace}
              />
            ))}
          </div>
        ) : (
          <div className="px-2 py-4 text-center">
            <BookOpen className="size-6 text-muted-foreground/20 mx-auto mb-2" />
            <p className="text-xs text-muted-foreground mb-2">No wiki yet</p>
            <a
              href="https://claude.ai"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Open Claude
              <ArrowUpRight className="size-3" />
            </a>
          </div>
        )}
      </div>

      {/* Back to workspace */}
      {workspaceSlug && (
        <div className="shrink-0 px-2 pb-1">
          <button
            onClick={() => router.push(`/workspaces/${workspaceSlug}`)}
            className="flex items-center gap-2 w-full px-2.5 py-2 text-[13px] rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors cursor-pointer"
          >
            <ArrowUpRight className="size-3.5 rotate-180" />
            <span className="flex-1 text-left">Back to workspace</span>
          </button>
        </div>
      )}

      {/* Sources button — separated from passive info below */}
      <div className="shrink-0 px-2 pb-1">
        <button
          onClick={onFilesToggle}
          className={cn(
            "flex items-center gap-2 w-full px-2.5 py-2 text-[13px] rounded-md transition-colors cursor-pointer",
            filesViewActive
              ? "bg-accent text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
          )}
        >
          <Library className="size-3.5" />
          <span className="flex-1 text-left">Sources</span>
          {sourceCount > 0 && (
            <span className="text-[10px] text-muted-foreground/30">
              {sourceCount}
            </span>
          )}
        </button>
      </div>

      {/* User menu */}
      <div className="shrink-0 border-t border-border p-2">
        <SidenavUserMenu />
      </div>
    </div>
  );
}

function SidenavSkeleton({ lines }: { lines: number }) {
  return (
    <div className="space-y-1 px-2 py-1">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-5 rounded-md bg-muted/50 animate-pulse"
          style={{ width: `${60 + Math.random() * 30}%` }}
        />
      ))}
    </div>
  );
}

function wikiNodeIcon(node: WikiNode, depth: number) {
  const slug = node.path?.replace(/\.(md|txt|json)$/, "").split("/")[0] ?? "";
  const titleLower = node.title.toLowerCase();

  if (slug === "overview" || (depth === 0 && titleLower === "overview"))
    return <BookOpen className="size-3 shrink-0 opacity-60" />;
  if (slug === "log" || (depth === 0 && titleLower === "log"))
    return <ScrollText className="size-3 shrink-0 opacity-60" />;
  if (slug === "concepts" || (depth === 0 && titleLower === "concepts"))
    return <Lightbulb className="size-3 shrink-0 opacity-60" />;
  if (slug === "entities" || (depth === 0 && titleLower === "entities"))
    return <Box className="size-3 shrink-0 opacity-60" />;

  if (depth > 0) return <FileText className="size-3 shrink-0 opacity-40" />;

  return <FileText className="size-3 shrink-0 opacity-50" />;
}

function WikiTreeNode({
  node,
  depth,
  activePath,
  onNavigate,
  onClose,
  kbId,
  onMoveToSpace,
  onCopyToSpace,
}: {
  node: WikiNode;
  depth: number;
  activePath: string | null;
  onNavigate: (path: string, docNumber?: number | null) => void;
  onClose?: () => void;
  kbId?: string;
  onMoveToSpace?: (docId: string, targetSpaceId: string) => void;
  onCopyToSpace?: (docId: string, targetSpaceId: string) => void;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isActive = node.path != null && node.path === activePath;
  const hasActiveChild =
    hasChildren && node.children!.some((c) => c.path === activePath);
  const [expanded, setExpanded] = React.useState(true);
  const [ctxMenu, setCtxMenu] = React.useState<{ x: number; y: number } | null>(
    null,
  );
  const [movePicker, setMovePicker] = React.useState(false);
  const [copyPicker, setCopyPicker] = React.useState(false);

  const handleContextMenu = (e: React.MouseEvent) => {
    if (!node.docId || !kbId) return;
    e.preventDefault();
    e.stopPropagation();
    setCtxMenu({ x: e.clientX, y: e.clientY });
  };

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1.5 w-full text-left text-[13px] rounded-md px-2 py-1.5 transition-colors cursor-pointer",
          isActive
            ? "bg-accent text-foreground font-medium"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onContextMenu={handleContextMenu}
        onClick={() => {
          if (node.path) {
            onNavigate(node.path, node.docNumber);
            onClose?.();
          } else if (hasChildren) {
            const first = node.children!.find((c) => c.path);
            if (first) {
              onNavigate(first.path!, first.docNumber);
              onClose?.();
            }
          }
        }}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((prev) => !prev);
            }}
            className="p-0.5 -ml-0.5 cursor-pointer"
          >
            <ChevronRight
              className={cn(
                "size-2.5 transition-transform duration-150",
                expanded && "rotate-90",
              )}
            />
          </button>
        ) : (
          <span className="w-3.5" />
        )}
        {wikiNodeIcon(node, depth)}
        <span className="truncate flex-1 min-w-0">{node.title}</span>
      </div>
      <AnimatePresence initial={false}>
        {hasChildren && (expanded || hasActiveChild) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15, ease: [0.25, 0.1, 0.25, 1] }}
            style={{ overflow: "hidden" }}
            className=""
          >
            {node.children!.map((child, i) => (
              <WikiTreeNode
                key={child.path ?? child.title ?? i}
                node={child}
                depth={depth + 1}
                activePath={activePath}
                onNavigate={onNavigate}
                onClose={onClose}
                kbId={kbId}
                onMoveToSpace={onMoveToSpace}
                onCopyToSpace={onCopyToSpace}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <WikiPageContextMenu
        open={!!ctxMenu}
        x={ctxMenu?.x ?? 0}
        y={ctxMenu?.y ?? 0}
        onClose={() => setCtxMenu(null)}
        onMoveToSpace={() => setMovePicker(true)}
        onCopyToSpace={() => setCopyPicker(true)}
      />
      {kbId && (
        <>
          <SpacePickerModal
            open={movePicker}
            onClose={() => setMovePicker(false)}
            currentSpaceId={kbId}
            title="Move to space"
            onConfirm={(sid) => {
              if (node.docId) onMoveToSpace?.(node.docId, sid);
            }}
          />
          <SpacePickerModal
            open={copyPicker}
            onClose={() => setCopyPicker(false)}
            currentSpaceId={kbId}
            title="Copy to space"
            onConfirm={(sid) => {
              if (node.docId) onCopyToSpace?.(node.docId, sid);
            }}
          />
        </>
      )}
    </div>
  );
}

function PageUsageBar() {
  const [usage, setUsage] = React.useState<Usage | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);

  React.useEffect(() => {
    apiFetch<Usage>("/v1/usage")
      .then(setUsage)
      .catch((err) => console.error("Usage load failed:", err));
  }, []);

  if (!usage) return null;

  const pct = Math.min(100, (usage.total_pages / usage.max_pages) * 100);
  const color =
    pct > 90 ? "bg-destructive" : pct > 70 ? "bg-yellow-500" : "bg-primary";

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className="flex items-center gap-2 w-full px-2 py-1 rounded-md hover:bg-accent transition-colors cursor-pointer group"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-[10px] text-muted-foreground/60 group-hover:text-muted-foreground transition-colors">
              Pages
            </span>
            <span className="text-[10px] font-mono text-muted-foreground/40 group-hover:text-muted-foreground/60 transition-colors">
              {usage.total_pages} / {usage.max_pages}
            </span>
          </div>
          <div className="h-1 rounded-full bg-muted overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", color)}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </button>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Page Usage</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>
              You've used{" "}
              <span className="font-medium text-foreground">
                {usage.total_pages.toLocaleString()}
              </span>{" "}
              of your{" "}
              <span className="font-medium text-foreground">
                {usage.max_pages.toLocaleString()}
              </span>{" "}
              page limit.
            </p>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", color)}
                style={{ width: `${pct}%` }}
              />
            </div>
            <p>
              Each PDF or office document consumes pages based on its length.
              Notes and wiki pages are free and unlimited.
            </p>
            <p className="text-xs text-muted-foreground/60">
              Individual documents are limited to 300 pages. Need more capacity?
              Contact us.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
