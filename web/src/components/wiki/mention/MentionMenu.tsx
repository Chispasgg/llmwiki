'use client'

import * as React from 'react'
import { createPortal } from 'react-dom'
import type { UserSuggestion } from '@/lib/shares'
import type { MentionSuggestionState } from './types'

interface MentionMenuProps {
  suggestion: MentionSuggestionState | null
  keyDownRef: React.MutableRefObject<((event: KeyboardEvent) => boolean) | null>
}

/**
 * Floating mention-autocomplete menu (mirrors SlashMenu pattern).
 *
 * Positioned via `clientRect` (cursor rect). Keyboard-navigable (↑ ↓ Enter Esc).
 * Uses `onMouseDown` (not `onClick`) so the editor never loses focus.
 *
 * Inserting a selection writes plain text `@<display_name> ` via the extension's
 * `command` callback — no TipTap nodes or marks are created.
 */
export function MentionMenu({ suggestion, keyDownRef }: MentionMenuProps) {
  const [selectedIndex, setSelectedIndex] = React.useState(0)

  const selectedIndexRef = React.useRef(0)
  const suggestionRef = React.useRef(suggestion)
  suggestionRef.current = suggestion

  const setIndex = React.useCallback((n: number) => {
    selectedIndexRef.current = n
    setSelectedIndex(n)
  }, [])

  // Reset selection when the item list changes.
  React.useEffect(() => {
    setIndex(0)
  }, [suggestion?.items, setIndex])

  // Register the keydown handler that the extension will call.
  React.useEffect(() => {
    keyDownRef.current = (event: KeyboardEvent): boolean => {
      const s = suggestionRef.current
      if (!s || s.items.length === 0) return false

      if (event.key === 'ArrowUp') {
        setIndex((selectedIndexRef.current - 1 + s.items.length) % s.items.length)
        return true
      }
      if (event.key === 'ArrowDown') {
        setIndex((selectedIndexRef.current + 1) % s.items.length)
        return true
      }
      if (event.key === 'Enter') {
        const item = s.items[selectedIndexRef.current]
        if (item) {
          s.command(item)
          return true
        }
        return false
      }
      // Esc is handled by @tiptap/suggestion natively; returning false lets it through.
      return false
    }

    return () => {
      keyDownRef.current = null
    }
  }, [keyDownRef, setIndex])

  // Hide when there is no active suggestion.
  if (!suggestion) return null

  const rect = suggestion.clientRect?.()
  if (!rect || typeof window === 'undefined') return null

  // Show a loading state while items are being fetched (empty array).
  const isEmpty = suggestion.items.length === 0

  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    top: rect.bottom + 4,
    left: Math.min(rect.left, window.innerWidth - 280),
    zIndex: 9999,
  }

  const handlePick = (item: UserSuggestion) => {
    suggestion.command(item)
  }

  return createPortal(
    <div
      role="listbox"
      aria-label="Mention users"
      style={menuStyle}
      className="bg-popover border border-border rounded-lg shadow-lg w-64 max-h-72 overflow-y-auto"
    >
      {isEmpty ? (
        <div className="px-3 py-2.5 text-sm text-muted-foreground">
          {suggestion.query.length === 0 ? 'Type a name…' : 'No users found'}
        </div>
      ) : (
        suggestion.items.map((item, index) => (
          <button
            key={item.id}
            role="option"
            aria-selected={index === selectedIndex}
            onMouseDown={(e) => {
              e.preventDefault()
              handlePick(item)
            }}
            className={[
              'w-full flex flex-col gap-0.5 px-3 py-2.5 text-left transition-colors cursor-pointer',
              index === selectedIndex
                ? 'bg-accent text-accent-foreground'
                : 'text-foreground hover:bg-accent/60',
            ].join(' ')}
          >
            <span className="text-sm font-medium leading-tight">
              {item.display_name}
            </span>
            <span className="text-xs text-muted-foreground">{item.email}</span>
          </button>
        ))
      )}
    </div>,
    document.body,
  )
}
