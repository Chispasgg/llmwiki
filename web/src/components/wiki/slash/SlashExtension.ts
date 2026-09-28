import { Extension } from '@tiptap/core'
import { PluginKey } from '@tiptap/pm/state'
import Suggestion from '@tiptap/suggestion'
import type { MutableRefObject } from 'react'
import type { SlashCommand, SlashSuggestionState } from './types'

const slashSuggestionPluginKey = new PluginKey('slashSuggestion')

/**
 * Creates a TipTap Extension that powers the `/` slash-command menu.
 *
 * All three refs are stable objects whose `.current` is kept up-to-date by
 * WikiEditor on every render — the extension only captures the ref objects
 * (created once), not the values inside them.
 */
export function createSlashExtension(
  dispatchRef: MutableRefObject<((state: SlashSuggestionState | null) => void) | null>,
  keyDownRef: MutableRefObject<((event: KeyboardEvent) => boolean) | null>,
  itemsRef: MutableRefObject<SlashCommand[]>,
) {
  return Extension.create({
    name: 'slashCommands',

    addProseMirrorPlugins() {
      return [
        Suggestion<SlashCommand, SlashCommand>({
          pluginKey: slashSuggestionPluginKey,
          editor: this.editor,
          char: '/',
          allowSpaces: false,
          startOfLine: false,

          items: ({ query }) => {
            const q = query.toLowerCase()
            if (!q) return itemsRef.current
            return itemsRef.current.filter(
              (item) =>
                item.title.toLowerCase().includes(q) ||
                item.description.toLowerCase().includes(q),
            )
          },

          // Called when the user selects an item from the menu.
          // `props` is the chosen SlashCommand.
          command: ({ editor, range, props }) => {
            props.execute(editor, range)
          },

          render: () => ({
            onStart(props) {
              dispatchRef.current?.({
                query: props.query,
                range: props.range,
                items: props.items,
                clientRect: props.clientRect ?? null,
                command: props.command,
              })
            },
            onUpdate(props) {
              dispatchRef.current?.({
                query: props.query,
                range: props.range,
                items: props.items,
                clientRect: props.clientRect ?? null,
                command: props.command,
              })
            },
            onKeyDown({ event }) {
              return keyDownRef.current?.(event) ?? false
            },
            onExit() {
              dispatchRef.current?.(null)
            },
          }),
        }),
      ]
    },
  })
}
