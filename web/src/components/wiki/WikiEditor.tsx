'use client'

import * as React from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Typography from '@tiptap/extension-typography'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import { Markdown } from 'tiptap-markdown'
import { NoteToolbar } from '@/components/editor/NoteToolbar'
import type { Editor } from '@tiptap/react'

export function getWikiMarkdown(editor: Editor): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (editor.storage as any).markdown.getMarkdown()
}

interface WikiEditorProps {
  /** Markdown content to load on mount */
  initialContent: string
  /** Title shown (read-only) in the toolbar */
  pageTitle: string
  /** Called once the TipTap editor instance is ready */
  onEditorReady?: (editor: Editor) => void
}

/**
 * Minimal WYSIWYG editor for wiki pages.
 * Reuses NoteToolbar for formatting; no autosave — parent controls Save/Cancel.
 */
export function WikiEditor({ initialContent, pageTitle, onEditorReady }: WikiEditorProps) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: false }),
      Placeholder.configure({ placeholder: 'Start writing...' }),
      Typography,
      Link.configure({ autolink: true, openOnClick: false }),
      Image.configure({ inline: false, allowBase64: true }),
      Markdown.configure({ html: false, transformCopiedText: true, transformPastedText: true }),
    ],
    content: initialContent,
    editorProps: {
      attributes: {
        class: 'prose prose-sm dark:prose-invert max-w-none focus:outline-none min-h-[400px] cursor-text',
      },
    },
  })

  // Expose editor to parent for Save action
  React.useEffect(() => {
    if (editor && onEditorReady) onEditorReady(editor)
  }, [editor, onEditorReady])

  // If parent passes new initialContent (e.g. page switch), reset the editor
  const prevContentRef = React.useRef(initialContent)
  React.useEffect(() => {
    if (editor && !editor.isDestroyed && initialContent !== prevContentRef.current) {
      prevContentRef.current = initialContent
      editor.commands.setContent(initialContent)
    }
  }, [editor, initialContent])

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Formatting toolbar — embedded mode: shows title (read-only) + formatting buttons */}
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
    </div>
  )
}
