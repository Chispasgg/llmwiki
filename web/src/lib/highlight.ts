/** Busca `quote` en los nodos de texto de `container`, hace scroll y un flash temporal.
 *  Devuelve false si no lo encuentra (comentario "sin ancla"). */
export function scrollToAndFlash(
  container: HTMLElement | null,
  quote: string | null,
): boolean {
  if (!container || !quote) return false;
  const needle = quote.trim();
  if (!needle) return false;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const idx = (node.textContent ?? "").indexOf(needle);
    if (idx >= 0) {
      const el = (node as Text).parentElement;
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("comment-flash");
        window.setTimeout(() => el.classList.remove("comment-flash"), 1500);
      }
      return true;
    }
  }
  return false;
}
