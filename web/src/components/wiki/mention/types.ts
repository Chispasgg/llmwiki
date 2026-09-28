import type { Range } from '@tiptap/core'
import type { UserSuggestion } from '@/lib/shares'

/** State passed from the TipTap mention suggestion callbacks to the React menu. */
export interface MentionSuggestionState {
  query: string
  range: Range
  items: UserSuggestion[]
  clientRect: (() => DOMRect | null) | null
  /** Call this with the chosen item to execute it and close the suggestion. */
  command: (item: UserSuggestion) => void
}
