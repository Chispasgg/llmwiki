import { describe, test, expect } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { refKind, extractLinks, renderBody } from './buzonRender'

// ── renderBody — guarda anti-XSS ──────────────────────────────────────────────

describe('renderBody — guarda anti-XSS', () => {
  test('esquema javascript: se renderiza como texto plano, sin <a>', () => {
    const markup = renderToStaticMarkup(renderBody('[xss](javascript:alert(1))') as React.ReactElement)
    expect(markup).not.toContain('<a')
    expect(markup).toContain('[xss](javascript:alert(1))')
  })

  test('URL https:// produce un <a> con href correcto', () => {
    const markup = renderToStaticMarkup(renderBody('[link](https://example.com)') as React.ReactElement)
    expect(markup).toContain('<a')
    expect(markup).toContain('href="https://example.com"')
  })

  test('esquema data: se renderiza como texto plano, sin <a>', () => {
    const markup = renderToStaticMarkup(renderBody('[img](data:text/html,<h1>xss</h1>)') as React.ReactElement)
    expect(markup).not.toContain('<a')
  })
})

// ── refKind ───────────────────────────────────────────────────────────────────

describe('refKind', () => {
  test('URL con /browse/ → jira', () => {
    expect(refKind('https://mycompany.atlassian.net/browse/PROJ-123')).toBe('jira')
  })

  test('URL con atlassian en el host → jira', () => {
    expect(refKind('https://mycompany.atlassian.net/jira/projects')).toBe('jira')
  })

  test('URL con jira en el path → jira', () => {
    expect(refKind('https://tools.example.com/jira/browse/TASK-1')).toBe('jira')
  })

  test('URL con /-/merge_requests/ → mr', () => {
    expect(refKind('https://gitlab.com/org/repo/-/merge_requests/42')).toBe('mr')
  })

  test('URL de gitlab sin merge_requests → link (no es MR)', () => {
    // Solo es mr si contiene /-/merge_requests/
    expect(refKind('https://gitlab.com/org/repo')).toBe('link')
  })

  test('URL con /wiki/ → wiki', () => {
    expect(refKind('https://myapp.example.com/wiki/page-name')).toBe('wiki')
  })

  test('URL normal sin heurística conocida → link', () => {
    expect(refKind('https://example.com/docs/readme')).toBe('link')
    expect(refKind('https://github.com/org/repo')).toBe('link')
    expect(refKind('https://notion.so/workspace/page')).toBe('link')
  })
})

// ── extractLinks ──────────────────────────────────────────────────────────────

describe('extractLinks', () => {
  test('extrae un enlace markdown http', () => {
    const body = 'Ver el ticket [PROJ-1](https://jira.example.com/browse/PROJ-1) para detalles'
    expect(extractLinks(body)).toEqual([
      { label: 'PROJ-1', url: 'https://jira.example.com/browse/PROJ-1' },
    ])
  })

  test('extrae varios enlaces en orden', () => {
    const body = 'Ticket [A](https://a.com) y MR [B](https://b.com/mr)'
    expect(extractLinks(body)).toEqual([
      { label: 'A', url: 'https://a.com' },
      { label: 'B', url: 'https://b.com/mr' },
    ])
  })

  test('ignora esquemas peligrosos: javascript:', () => {
    const body = 'Clic [aquí](javascript:alert(1)) para ejecutar'
    expect(extractLinks(body)).toEqual([])
  })

  test('ignora esquemas peligrosos: data:', () => {
    const body = 'Imagen [img](data:text/html,<h1>xss</h1>)'
    expect(extractLinks(body)).toEqual([])
  })

  test('ignora texto que no es enlace markdown', () => {
    const body = 'Texto plano sin enlace'
    expect(extractLinks(body)).toEqual([])
  })

  test('no extrae URL solas (sin formato markdown)', () => {
    const body = 'URL directa: https://example.com sin corchetes'
    expect(extractLinks(body)).toEqual([])
  })

  test('cuerpo vacío → lista vacía', () => {
    expect(extractLinks('')).toEqual([])
  })
})
