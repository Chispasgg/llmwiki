"use client";

/**
 * ExcalidrawNode — TipTap node extension for Excalidraw diagrams.
 *
 * Round-trip contract (tiptap-markdown ↔ markdown):
 *   Serialize : excalidraw node  →  ```excalidraw\n<JSON>\n```
 *   Parse     : ```excalidraw block  →  div[data-type="excalidraw" data-scene="..."]
 *               ↓ (TipTap parseHTML rule)
 *               excalidraw node
 *
 * The parse path hooks markdown-it's fence renderer (in addStorage.markdown.parse.setup)
 * to intercept fences whose info string is "excalidraw" and emit a custom <div> instead
 * of the default <pre><code>. TipTap's schema parseHTML rule then maps that div back to
 * an `excalidraw` node.
 *
 * Command: editor.commands.insertExcalidraw(scene?)
 * NodeView: ExcalidrawNodeView (preview SVG + edit modal)
 */

import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";
import type { MarkdownNodeSpec } from "tiptap-markdown";
import type MarkdownIt from "markdown-it";
import { ExcalidrawNodeView } from "./ExcalidrawNodeView";

// ---------------------------------------------------------------------------
// Command declarations
// ---------------------------------------------------------------------------

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    excalidraw: {
      /**
       * Insert an excalidraw diagram node at the current cursor position.
       * @param scene – optional JSON string of an ExcalidrawScene. Defaults to empty scene.
       */
      insertExcalidraw: (scene?: string) => ReturnType;
    };
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export const ExcalidrawNode = Node.create({
  name: "excalidraw",

  /** Block-level, leaf (atom), draggable. */
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,

  // ── Attributes ─────────────────────────────────────────────────────────────

  addAttributes() {
    return {
      /**
       * JSON string of the Excalidraw scene ({ elements, appState?, files? }).
       * Stored as the `data-scene` attribute on the wrapper div when converted to DOM.
       */
      scene: {
        default: '{"elements":[]}',
        parseHTML: (element) =>
          element.getAttribute("data-scene") ?? '{"elements":[]}',
        renderHTML: (attributes) => ({
          "data-scene": attributes.scene as string,
        }),
      },
    };
  },

  // ── DOM parse / render ──────────────────────────────────────────────────────

  parseHTML() {
    return [{ tag: 'div[data-type="excalidraw"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes({ "data-type": "excalidraw" }, HTMLAttributes)];
  },

  // ── tiptap-markdown integration ─────────────────────────────────────────────

  addStorage() {
    const markdown: MarkdownNodeSpec = {
      /**
       * Serialize the node to a ```excalidraw fenced code block.
       * Called by tiptap-markdown's MarkdownSerializer when getMarkdown() is invoked.
       */
      serialize(state, node) {
        state.write("```excalidraw\n");
        state.write((node.attrs as { scene: string }).scene ?? '{"elements":[]}');
        state.ensureNewLine();
        state.write("```");
        state.closeBlock(node);
      },

      parse: {
        /**
         * Hook markdown-it's fence renderer to intercept ```excalidraw blocks.
         *
         * Parse flow (tiptap-markdown):
         *   1. setup(md) configures markdown-it (called on each parse() invocation)
         *   2. md.render(content) → HTML string
         *   3. TipTap parses HTML via schema parseHTML rules
         *
         * We override md.renderer.rules.fence so that fences with info "excalidraw"
         * produce <div data-type="excalidraw" data-scene="..."> instead of
         * <pre><code class="language-excalidraw">. The parseHTML rule above then
         * matches that div and returns an excalidraw node.
         *
         * The _excalidrawPatched guard ensures idempotency: the MarkdownParser
         * instance is long-lived but setup() is called on every parse() invocation.
         */
        setup(md: MarkdownIt) {
          const mdExt = md as MarkdownIt & { _excalidrawPatched?: boolean };
          if (mdExt._excalidrawPatched) return;
          mdExt._excalidrawPatched = true;

          const original = md.renderer.rules.fence;

          md.renderer.rules.fence = (tokens, idx, options, env, self) => {
            const token = tokens[idx];
            const info = token.info.trim().toLowerCase();

            if (info === "excalidraw") {
              const json = token.content.trim();
              // Escape for safe embedding inside a double-quoted HTML attribute.
              // The browser's attribute parser automatically un-escapes these
              // when element.getAttribute() is called.
              const escaped = json
                .replace(/&/g, "&amp;")
                .replace(/"/g, "&quot;");
              return `<div data-type="excalidraw" data-scene="${escaped}"></div>`;
            }

            // Delegate to the previously set rule (already wrapped by
            // tiptap-markdown's withPatchedRenderer for newline stripping).
            if (original) {
              return original(tokens, idx, options, env, self);
            }
            return self.renderToken(tokens, idx, options);
          };
        },
      },
    };

    return { markdown };
  },

  // ── Commands ────────────────────────────────────────────────────────────────

  addCommands() {
    return {
      insertExcalidraw:
        (scene?: string) =>
        ({ commands }) => {
          return commands.insertContent({
            type: this.name,
            attrs: { scene: scene ?? '{"elements":[]}' },
          });
        },
    };
  },

  // ── NodeView ────────────────────────────────────────────────────────────────

  addNodeView() {
    return ReactNodeViewRenderer(ExcalidrawNodeView);
  },
});
