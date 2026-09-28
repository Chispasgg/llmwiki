import { Extension } from '@tiptap/core'
import { PluginKey } from '@tiptap/pm/state'
import Suggestion from '@tiptap/suggestion'
import type { MutableRefObject } from 'react'
import type { UserSuggestion } from '@/lib/shares'
import type { MentionSuggestionState } from './types'

const mentionSuggestionPluginKey = new PluginKey('mentionSuggestion')

/**
 * Creates a TipTap Extension that powers the `@` mention autocomplete.
 *
 * When the user types `@` followed by text, it debounces a call to
 * `fetchUsers(query)` and updates the floating menu via `dispatchRef`.
 *
 * On selection, it deletes the `@query` range and inserts plain text
 * `@<display_name> ` — no custom nodes, no marks — so tiptap-markdown
 * serialises it as ordinary Markdown text.
 */
export function createMentionExtension(
  dispatchRef: MutableRefObject<((state: MentionSuggestionState | null) => void) | null>,
  keyDownRef: MutableRefObject<((event: KeyboardEvent) => boolean) | null>,
  fetchUsers: (query: string) => Promise<UserSuggestion[]>,
) {
  // Holds the latest suggestion props so the async fetch can reconstruct state.
  let latestProps: {
    query: string
    range: { from: number; to: number }
    clientRect: (() => DOMRect | null) | null
    command: (item: UserSuggestion) => void
  } | null = null

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function triggerFetch(query: string) {
    if (debounceTimer !== null) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      fetchUsers(query)
        .then((results) => {
          if (!latestProps) return
          dispatchRef.current?.({
            query: latestProps.query,
            range: latestProps.range,
            items: results,
            clientRect: latestProps.clientRect,
            command: latestProps.command,
          })
        })
        .catch(() => {
          // Leave menu unchanged on error.
        })
    }, 200)
  }

  return Extension.create({
    name: 'mentionSuggestion',

    addProseMirrorPlugins() {
      return [
        Suggestion<UserSuggestion, UserSuggestion>({
          pluginKey: mentionSuggestionPluginKey,
          editor: this.editor,
          char: '@',
          allowSpaces: false,
          startOfLine: false,

          // items() must return synchronously; return [] immediately and
          // populate async via the debounced fetch + dispatchRef.
          items: () => [],

          command: ({ editor, range, props }) => {
            editor
              .chain()
              .focus()
              .deleteRange(range)
              .insertContent([
                {
                  type: 'text',
                  text: `@${props.display_name}`,
                  marks: [{ type: 'link', attrs: { href: `mention:${props.id}` } }],
                },
                { type: 'text', text: ' ' },
              ])
              .run()
          },

          render: () => ({
            onStart(props) {
              latestProps = {
                query: props.query,
                range: props.range,
                clientRect: props.clientRect ?? null,
                command: props.command,
              }
              // Show empty menu immediately, then populate via debounce.
              dispatchRef.current?.({
                query: props.query,
                range: props.range,
                items: [],
                clientRect: props.clientRect ?? null,
                command: props.command,
              })
              triggerFetch(props.query)
            },
            onUpdate(props) {
              latestProps = {
                query: props.query,
                range: props.range,
                clientRect: props.clientRect ?? null,
                command: props.command,
              }
              // Dispatch with empty items; debounce will fill them in.
              dispatchRef.current?.({
                query: props.query,
                range: props.range,
                items: props.items,
                clientRect: props.clientRect ?? null,
                command: props.command,
              })
              triggerFetch(props.query)
            },
            onKeyDown({ event }) {
              return keyDownRef.current?.(event) ?? false
            },
            onExit() {
              if (debounceTimer !== null) {
                clearTimeout(debounceTimer)
                debounceTimer = null
              }
              latestProps = null
              dispatchRef.current?.(null)
            },
          }),
        }),
      ]
    },
  })
}
