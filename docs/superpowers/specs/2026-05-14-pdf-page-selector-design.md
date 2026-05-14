# PDF Page Selector — Design Spec

## Goal

Before generating the PDF, show a dialog that lets the user choose which wiki pages to include. All pages are selected by default. Parent nodes have a tri-state checkbox that selects/deselects all their children at once.

## Architecture

The selection state lives entirely in the frontend dialog component. The selected page identifiers (`document_number`) are sent to the backend in a POST body. The backend filters the document list before building the combined Markdown, so the generated TOC reflects exactly what was selected.

## Tech Stack

- Frontend: React 19, Next.js 16, shadcn/ui Dialog, lucide-react, Tailwind CSS
- Backend: FastAPI, Pydantic, existing `ExportService`

---

## Frontend

### New component: `ExportPdfDialog`

**File:** `web/src/components/kb/ExportPdfDialog.tsx`

**Props:**
```typescript
interface ExportPdfDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kbId: string
  kbName: string
  wikiTree: WikiNode[]
  onExport: (docNumbers: number[]) => void
  loading: boolean
}
```

**State:**
- `selected: Set<number>` — set of `docNumber` values currently checked. Initialised with all leaf `docNumber`s from `wikiTree` on first open.

**Checkbox semantics:**
- **Leaf node** (has `path` and `docNumber`): simple checkbox, toggles its `docNumber` in `selected`.
- **Parent node** (has `children`, may or may not have its own `path`):
  - `checked` if all descendant leaf `docNumber`s are in `selected`
  - `indeterminate` if some (but not all) are in `selected`
  - `unchecked` if none are in `selected`
  - Clicking a parent in any state: if fully checked → uncheck all descendants; otherwise → check all descendants.

**"Seleccionar todo" / "Deseleccionar todo":** buttons above the tree that set `selected` to all leaf doc numbers or to an empty set.

**Footer:**
- "Cancelar" — closes dialog, resets selection to all selected.
- "Generar PDF" — calls `onExport(Array.from(selected))`. Disabled if `selected` is empty or `loading` is true. Shows doc count: `"Generar PDF (N páginas)"`.

**Scroll:** tree section is `overflow-y-auto` with a `max-h` so the dialog doesn't exceed the viewport on large wikis.

### Helper: `collectLeafDocNumbers(nodes: WikiNode[]): number[]`

Recursively collects all `docNumber` values from nodes that have both `path` and a non-null `docNumber`. Used to initialise `selected` and for parent checkbox state calculation.

### Modified: `KBSidenav.tsx`

- Add state: `exportDialogOpen: boolean`
- Remove state: `exportLoading` (moved to dialog)
- "Exportar PDF" button in the actions dropdown sets `exportDialogOpen = true` (no longer calls `handleExportPdf` directly).
- `handleExportPdf(docNumbers: number[])` is passed as `onExport` prop to the dialog. It closes the dialog, then does the fetch (POST instead of GET), download, and toast.

### API call change

**Before:** `GET /v1/knowledge-bases/{kb_id}/export.pdf`

**After:** `POST /v1/knowledge-bases/{kb_id}/export.pdf` with JSON body:
```json
{ "doc_numbers": [1, 3, 5, 7] }
```

`doc_numbers: null` or omitted means "all wiki pages" (backend default).

`Content-Type: application/json`. Response is still `application/pdf` binary.

---

## Backend

### Modified: `routes/export.py`

Add request body model:
```python
class ExportRequest(BaseModel):
    doc_numbers: list[int] | None = None
```

Change decorator from `@router.get` to `@router.post`. Add `body: ExportRequest` parameter. Pass `body.doc_numbers` to `export_service.generate_pdf()`.

### Modified: `services/export.py`

`generate_pdf()` gets a new optional parameter:
```python
async def generate_pdf(
    self,
    kb_id: str,
    user_id: str,
    kb_name: str,
    template_path: Path,
    doc_numbers: list[int] | None = None,
) -> bytes:
```

After sorting docs, filter if `doc_numbers` is provided:
```python
if doc_numbers is not None:
    allowed = set(doc_numbers)
    docs = [d for d in docs if d.get("document_number") in allowed]
```

---

## Data flow

```
User clicks "Exportar PDF"
  → ExportPdfDialog opens (all pages pre-selected)
  → User deselects some pages
  → User clicks "Generar PDF (N páginas)"
    → onExport([1, 3, 5]) called
    → Dialog closes, loading starts
    → POST /v1/knowledge-bases/{kb_id}/export.pdf { doc_numbers: [1,3,5] }
    → ExportService fetches all wiki docs, filters to [1,3,5]
    → Builds combined.md with only those docs (in sort order)
    → pandoc generates PDF with correct TOC
    → Browser downloads PDF
```

---

## What is NOT in scope

- Remembering previous selections between sessions
- Custom page ordering (sort order is always the standard wiki order)
- Filtering by tag or content
- Preview of the PDF before download
- Exporting source documents (non-wiki files)
