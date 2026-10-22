import { describe, test, expect } from 'bun:test'
import { hueFromName, estadoToChip, plazoToChip } from './buzonFormat'

// Fecha fija inyectada para que los tests de plazo sean deterministas.
// 22 de octubre de 2026, mediodía.
const NOW = new Date(2026, 9, 22, 12, 0, 0)

// ── hueFromName ───────────────────────────────────────────────────────────────

describe('hueFromName', () => {
  test('devuelve el mismo tono para el mismo nombre (determinista)', () => {
    expect(hueFromName('Ana García')).toBe(hueFromName('Ana García'))
  })

  test('el resultado está en el rango [0, 360)', () => {
    const samples = ['Alice', 'Bob', 'Carlos López', '', 'X', 'ZZZZZZZZZZZZ']
    for (const s of samples) {
      const h = hueFromName(s)
      expect(h).toBeGreaterThanOrEqual(0)
      expect(h).toBeLessThan(360)
    }
  })

  test('nombres distintos producen tonos distintos en general', () => {
    const alice = hueFromName('Alice')
    const bob = hueFromName('Bob')
    const carol = hueFromName('Carol')
    // No garantizamos colisión cero, pero estos tres nombres concretos deben diferir.
    expect(alice).not.toBe(bob)
    expect(alice).not.toBe(carol)
    expect(bob).not.toBe(carol)
  })
})

// ── estadoToChip ──────────────────────────────────────────────────────────────

describe('estadoToChip', () => {
  test('vacío → new', () => {
    expect(estadoToChip([])).toEqual({ variant: 'new', label: 'nuevo' })
  })

  test('solo visto → seen', () => {
    expect(estadoToChip(['visto'])).toEqual({ variant: 'seen', label: 'visto' })
  })

  test('aceptado gana a visto', () => {
    expect(estadoToChip(['visto', 'aceptado'])).toEqual({ variant: 'accepted', label: 'aceptado' })
  })

  test('hecho gana a aceptado', () => {
    expect(estadoToChip(['aceptado', 'hecho'])).toEqual({ variant: 'done', label: 'hecho' })
  })

  test('rechazado gana a hecho', () => {
    expect(estadoToChip(['hecho', 'rechazado'])).toEqual({ variant: 'rejected', label: 'rechazado' })
  })

  test('case-insensitive', () => {
    expect(estadoToChip(['RECHAZADO'])).toEqual({ variant: 'rejected', label: 'rechazado' })
    expect(estadoToChip(['Hecho'])).toEqual({ variant: 'done', label: 'hecho' })
  })
})

// ── plazoToChip ───────────────────────────────────────────────────────────────

describe('plazoToChip', () => {
  test('null → null', () => {
    expect(plazoToChip(null, NOW)).toBeNull()
  })

  test('cadena malformada → null', () => {
    expect(plazoToChip('no-es-fecha', NOW)).toBeNull()
    expect(plazoToChip('abc', NOW)).toBeNull()
    expect(plazoToChip('/', NOW)).toBeNull()
  })

  test('fecha pasada → over', () => {
    // 10/10 (10 de octubre 2026) es anterior al 22/10/2026
    expect(plazoToChip('10/10', NOW)).toEqual({ variant: 'over', label: 'vencido' })
  })

  test('fecha dentro de 3 días → soon', () => {
    // 23/10 (23 de octubre 2026): deadline 23:59:59 → ~36h desde mediodía del 22/10 < 3 días
    expect(plazoToChip('23/10', NOW)).toEqual({ variant: 'soon', label: 'próximo' })
  })

  test('fecha lejana → null', () => {
    // 01/12 (1 de diciembre 2026) está muy lejos del 22/10/2026
    expect(plazoToChip('01/12', NOW)).toBeNull()
  })
})
