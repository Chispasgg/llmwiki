import type { Editor, Range } from '@tiptap/core'

/** One item in the slash command menu. */
export interface SlashCommand {
  id: string
  title: string
  description: string
  /** Called with the editor and the text range occupied by the `/` trigger. */
  execute: (editor: Editor, range: Range) => void
}

/** State passed from the TipTap suggestion callbacks to the React menu component. */
export interface SlashSuggestionState {
  query: string
  range: Range
  items: SlashCommand[]
  clientRect: (() => DOMRect | null) | null
  /** Call this with the chosen item to execute it and close the suggestion. */
  command: (item: SlashCommand) => void
}
