'use client'

import * as React from 'react'
import { createPortal } from 'react-dom'
import type { SlashCommand, SlashSuggestionState } from './types'

interface SlashMenuProps {
  suggestion: SlashSuggestionState | null
  keyDownRef: React.MutableRefObject<((event: KeyboardEvent) => boolean) | null>
}

/**
 * Floating slash-command menu.
 *
 * Positioned via `clientRect` (cursor rect). Keyboard-navigable (↑ ↓ Enter).
 * Uses `onMouseDown` (not `onClick`) so the editor never loses focus when the
 * user picks an item with the mouse.
 */
export function SlashMenu({ suggestion, keyDownRef }: SlashMenuProps) {
  const [selectedIndex, setSelectedIndex] = React.useState(0)

  // Refs to avoid stale closures inside the keydown handler.
  const selectedIndexRef = React.useRef(0)
  const suggestionRef = React.useRef(suggestion)
  suggestionRef.current = suggestion

  const setIndex = React.useCallback((n: number) => {
    selectedIndexRef.current = n
    setSelectedIndex(n)
  }, [])

  // Reset selection whenever the query (and therefore the item list) changes.
  React.useEffect(() => {
    setIndex(0)
  }, [suggestion?.query, setIndex])

  // Register the keydown handler that the extension will call.
  // Written to a ref so the handler always reads fresh state without deps.
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
      return false
    }

    return () => {
      keyDownRef.current = null
    }
  }, [keyDownRef, setIndex])

  // Nothing to show: no active suggestion or no matching items.
  if (!suggestion || suggestion.items.length === 0) return null

  const rect = suggestion.clientRect?.()
  if (!rect || typeof window === 'undefined') return null

  const menuStyle: React.CSSProperties = {
    position: 'fixed',
    top: rect.bottom + 4,
    left: Math.min(rect.left, window.innerWidth - 296),
    zIndex: 9999,
  }

  const handlePick = (item: SlashCommand) => {
    suggestion.command(item)
  }

  return createPortal(
    <div
      role="listbox"
      aria-label="Slash commands"
      style={menuStyle}
      className="bg-popover border border-border rounded-lg shadow-lg w-72 max-h-80 overflow-y-auto"
    >
      {suggestion.items.map((item, index) => (
        <button
          key={item.id}
          role="option"
          aria-selected={index === selectedIndex}
          // onMouseDown prevents the editor from blurring before we execute.
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
          <span className="text-sm font-medium leading-tight">{item.title}</span>
          <span className="text-xs text-muted-foreground">{item.description}</span>
        </button>
      ))}
    </div>,
    document.body,
  )
}
