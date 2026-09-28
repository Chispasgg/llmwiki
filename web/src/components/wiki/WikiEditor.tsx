'use client'

import * as React from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Typography from '@tiptap/extension-typography'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import { Markdown } from 'tiptap-markdown'
import { ExcalidrawNode } from './excalidraw/ExcalidrawNode'
import { NoteToolbar } from '@/components/editor/NoteToolbar'
import { SlashMenu } from './slash/SlashMenu'
import { PagePicker } from './slash/PagePicker'
import { createSlashExtension } from './slash/SlashExtension'
import type { SlashCommand, SlashSuggestionState } from './slash/types'
import { MentionMenu } from './mention/MentionMenu'
import { createMentionExtension } from './mention/MentionExtension'
import type { MentionSuggestionState } from './mention/types'
import { searchUsers } from '@/lib/shares'
import type { Editor } from '@tiptap/react'
import type { DocumentListItem } from '@/lib/types'

export function getWikiMarkdown(editor: Editor): string {
  // editor.storage is typed as the Web Storage API type; cast via unknown first.
  return (editor.storage as unknown as { markdown: { getMarkdown: () => string } }).markdown.getMarkdown()
}

interface WikiEditorProps {
  /** Markdown content to load on mount. */
  initialContent: string
  /** Title shown (read-only) in the toolbar. */
  pageTitle: string
  /** Called once the TipTap editor instance is ready. */
  onEditorReady?: (editor: Editor) => void
  /** Wiki documents exposed to the internal-link page picker. */
  documents?: DocumentListItem[]
}

/**
 * WYSIWYG editor for wiki pages.
 *
 * Features:
 * - All StarterKit blocks + Table
 * - Slash command menu (type `/`) to insert blocks and internal links
 * - Round-trips faithfully through tiptap-markdown: every block serialises
 *   to standard Markdown; the internal-link item produces [title](path).
 */
export function WikiEditor({
  initialContent,
  pageTitle,
  onEditorReady,
  documents = [],
}: WikiEditorProps) {
  // ── Slash-menu state ─────────────────────────────────────────────────────────
  const [slashSuggestion, setSlashSuggestion] = React.useState<SlashSuggestionState | null>(null)
  const [linkPickerOpen, setLinkPickerOpen] = React.useState(false)

  // Stable ref objects.  Their .current values are updated every render so the
  // extension (created once) always sees the latest callbacks without needing
  // to be recreated.
  const dispatchRef = React.useRef<((state: SlashSuggestionState | null) => void) | null>(null)
  const keyDownRef = React.useRef<((event: KeyboardEvent) => boolean) | null>(null)
  const itemsRef = React.useRef<SlashCommand[]>([])
  const openLinkPickerRef = React.useRef<() => void>(() => {})

  // ── Mention-menu state ───────────────────────────────────────────────────────
  const [mentionSuggestion, setMentionSuggestion] =
    React.useState<MentionSuggestionState | null>(null)
  const mentionDispatchRef = React.useRef<
    ((state: MentionSuggestionState | null) => void) | null
  >(null)
  const mentionKeyDownRef = React.useRef<((event: KeyboardEvent) => boolean) | null>(null)

  // Keep dispatch and openLinkPicker refs current on every render.
  dispatchRef.current = setSlashSuggestion
  openLinkPickerRef.current = () => setLinkPickerOpen(true)
  mentionDispatchRef.current = setMentionSuggestion

  // Slash command definitions.  The "link-page" item reads openLinkPickerRef at
  // call-time so it always has the current setter even though items are built once.
  const slashItems = React.useMemo(
    (): SlashCommand[] => [
      {
        id: 'heading1',
        title: 'Heading 1',
        description: 'Large section title',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleHeading({ level: 1 }).run(),
      },
      {
        id: 'heading2',
        title: 'Heading 2',
        description: 'Medium section title',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleHeading({ level: 2 }).run(),
      },
      {
        id: 'heading3',
        title: 'Heading 3',
        description: 'Small section title',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleHeading({ level: 3 }).run(),
      },
      {
        id: 'bullet',
        title: 'Bullet list',
        description: 'Unordered list with bullets',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleBulletList().run(),
      },
      {
        id: 'ordered',
        title: 'Numbered list',
        description: 'Ordered list with numbers',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
      },
      {
        id: 'blockquote',
        title: 'Quote',
        description: 'Highlighted block quotation',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleBlockquote().run(),
      },
      {
        id: 'code',
        title: 'Code block',
        description: 'Preformatted code fence',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
      },
      {
        id: 'table',
        title: 'Table',
        description: 'Insert a 3×3 table',
        execute: (editor, range) =>
          editor
            .chain()
            .focus()
            .deleteRange(range)
            .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
            .run(),
      },
      {
        id: 'divider',
        title: 'Divider',
        description: 'Horizontal rule separator',
        execute: (editor, range) =>
          editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
      },
      {
        id: 'link-page',
        title: 'Link page…',
        description: 'Insert link to another wiki page',
        execute: (editor, range) => {
          // Delete the trigger range so cursor is in the right place, then open
          // the picker.  Insertion happens in handleInsertLink.
          editor.chain().focus().deleteRange(range).run()
          openLinkPickerRef.current()
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  // Keep itemsRef in sync so the extension always sees the latest filtered list.
  itemsRef.current = slashItems

  // ── Slash extension (created once, captures stable refs) ─────────────────────
  const [slashExtension] = React.useState(() =>
    createSlashExtension(dispatchRef, keyDownRef, itemsRef),
  )

  // ── Mention extension (created once, captures stable refs) ───────────────────
  const [mentionExtension] = React.useState(() =>
    createMentionExtension(mentionDispatchRef, mentionKeyDownRef, searchUsers),
  )

  // ── TipTap editor ─────────────────────────────────────────────────────────────
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false }),
      Placeholder.configure({ placeholder: 'Start writing… Type / for commands' }),
      Typography,
      Link.configure({ autolink: true, openOnClick: false, protocols: ['mention'] }),
      Image.configure({ inline: false, allowBase64: true }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      ExcalidrawNode,
      Markdown.configure({ html: false, transformCopiedText: true, transformPastedText: true }),
      slashExtension,
      mentionExtension,
    ],
    content: initialContent,
    editorProps: {
      attributes: {
        class:
          'prose prose-sm dark:prose-invert max-w-none focus:outline-none min-h-[400px] cursor-text',
      },
    },
  })

  // Expose editor to parent for Save action.
  React.useEffect(() => {
    if (editor && onEditorReady) onEditorReady(editor)
  }, [editor, onEditorReady])

  // Reset when the parent switches to a different page.
  const prevContentRef = React.useRef(initialContent)
  React.useEffect(() => {
    if (editor && !editor.isDestroyed && initialContent !== prevContentRef.current) {
      prevContentRef.current = initialContent
      editor.commands.setContent(initialContent)
    }
  }, [editor, initialContent])

  // ── Internal-link insertion ───────────────────────────────────────────────────
  // Called when the user picks a page from PagePicker.
  // Inserts a TipTap link node so tiptap-markdown serialises it as [title](path).
  const handleInsertLink = React.useCallback(
    (doc: DocumentListItem) => {
      if (!editor) return
      const path = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
      const title = doc.title || doc.filename.replace(/\.(md|txt)$/, '')
      editor
        .chain()
        .focus()
        .insertContent({
          type: 'text',
          text: title,
          marks: [{ type: 'link', attrs: { href: path } }],
        })
        .run()
      setLinkPickerOpen(false)
    },
    [editor],
  )

  return (
    <div className="h-full flex flex-col min-h-0">
      <NoteToolbar
        editor={editor}
        backLabel=""
        noteTitle={pageTitle}
        embedded
        onBack={() => {}}
      />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        <EditorContent editor={editor} />
      </div>

      {/* Floating slash-command menu (rendered via portal to document.body) */}
      <SlashMenu suggestion={slashSuggestion} keyDownRef={keyDownRef} />

      {/* Floating mention autocomplete menu */}
      <MentionMenu suggestion={mentionSuggestion} keyDownRef={mentionKeyDownRef} />

      {/* Page-picker dialog for the "Link page…" slash command */}
      <PagePicker
        open={linkPickerOpen}
        documents={documents}
        onSelect={handleInsertLink}
        onClose={() => setLinkPickerOpen(false)}
      />
    </div>
  )
}
