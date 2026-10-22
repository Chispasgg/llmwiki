import { describe, test, expect } from 'bun:test'
import { dayLabel, groupByDay, type BuzonRow } from './buzonListHelpers'
import type { ParsedMessage } from './buzonTypes'

// Fecha fija inyectada para que los tests sean deterministas.
// 22 de octubre de 2026, mediodía.
const NOW = new Date(2026, 9, 22, 12, 0, 0)

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeParsed(fecha: string): ParsedMessage {
  return {
    closed: false,
    id: `${fecha}-1200-a-b`,
    id_parts: { fecha, hora: '1200', remitente: 'a', destinatario: 'b', b: false },
    tipo: 'Mensaje',
    reply_to: null,
    plazo: null,
    body: 'cuerpo',
    estados: [],
  }
}

function row(fecha: string | null, key: string): BuzonRow {
  return {
    key,
    id: key,
    who: 'Test',
    raw: 'texto crudo',
    parsed: fecha ? makeParsed(fecha) : null,
  }
}

// ── dayLabel ──────────────────────────────────────────────────────────────────

describe('dayLabel', () => {
  test('devuelve HOY para la fecha de hoy (YYYYMMDD)', () => {
    expect(dayLabel('20261022', NOW)).toBe('HOY')
  })

  test('devuelve AYER para el día anterior', () => {
    expect(dayLabel('20261021', NOW)).toBe('AYER')
  })

  test('devuelve DD/MM/YYYY para fechas más antiguas', () => {
    expect(dayLabel('20261010', NOW)).toBe('10/10/2026')
  })

  test('rellena con cero los días y meses de un dígito', () => {
    expect(dayLabel('20260101', NOW)).toBe('01/01/2026')
  })

  test('fecha malformada devuelve el string original sin transformar', () => {
    // Longitud distinta de 8 → pasa sin procesar
    expect(dayLabel('abc', NOW)).toBe('abc')
  })
})

// ── groupByDay ────────────────────────────────────────────────────────────────

describe('groupByDay', () => {
  test('rows del mismo día van en el mismo grupo', () => {
    const rows = [row('20261022', 'a'), row('20261022', 'b')]
    const groups = groupByDay(rows, NOW)
    expect(groups).toHaveLength(1)
    expect(groups[0].rows).toHaveLength(2)
    expect(groups[0].label).toBe('HOY')
  })

  test('rows de días distintos van en grupos separados', () => {
    const rows = [row('20261022', 'a'), row('20261021', 'b'), row('20261010', 'c')]
    const groups = groupByDay(rows, NOW)
    expect(groups).toHaveLength(3)
    expect(groups[0].label).toBe('HOY')
    expect(groups[1].label).toBe('AYER')
    expect(groups[2].label).toBe('10/10/2026')
  })

  test('orden de grupos es estable (primer fecha encontrada primero)', () => {
    const rows = [row('20261021', 'b'), row('20261022', 'a')]
    const groups = groupByDay(rows, NOW)
    expect(groups[0].label).toBe('AYER')
    expect(groups[1].label).toBe('HOY')
  })

  test('rows sin parsed van en un grupo final "Sin fecha"', () => {
    const rows = [row('20261022', 'a'), row(null, 'x'), row('20261021', 'b'), row(null, 'y')]
    const groups = groupByDay(rows, NOW)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('Sin fecha')
    expect(last.rows).toHaveLength(2)
  })

  test('rows solo sin fecha producen un único grupo "Sin fecha"', () => {
    const rows = [row(null, 'x'), row(null, 'y')]
    const groups = groupByDay(rows, NOW)
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Sin fecha')
  })

  test('lista vacía devuelve array vacío', () => {
    expect(groupByDay([], NOW)).toHaveLength(0)
  })
})
