"""Unit tests for the buzón line parser (BZ-001).

Tests are written before the implementation (TDD: RED first, then GREEN).
Every test names the production change that would make it fail.
"""

from datetime import datetime

import pytest

from services.buzon.parser import (
    IdParts,
    ParsedLine,
    append_estado,
    build_line,
    extract_id,
    parse_line,
    set_closed,
)

# ── Unicode separators (mirror exactly what the norma requires) ───────────────
_SEP = " · "  # " · "  FIELD SEPARATOR  (U+00B7 MIDDLE DOT)
_DASH = " — "  # " — "  BODY SEPARATOR   (U+2014 EM DASH)


# ── Canonical example lines from the norma (spec §Formato EXACTO) ────────────

LINE_TAREA_4PARTS = (
    "- [ ] 20261019-2015-tayfun-patxi"
    + _SEP
    + "Tarea"
    + _SEP
    + "plazo 23/10"
    + _DASH
    + "Revisar el MR !7 de identity"
    + _SEP
    + "[MR !7](https://example.com/mr7)"
)

LINE_RESPUESTA = (
    "- [ ] 20261019-2130-patxi-tayfun"
    + _SEP
    + "Respuesta a 20261019-2015-tayfun-patxi"
    + _DASH
    + "Visto, lo miro el miércoles"
)

LINE_TAREA_3PARTS_CLOSED = (
    "- [x] 20261020-1303-miguel"
    + _SEP
    + "Tarea"
    + _DASH
    + "MR para revisar, la 1032: kb-mcp !6, runtime !101"
    + _SEP
    + "[kb-mcp !6](https://example.com/kbmcp)"
    + _SEP
    + "[runtime !101](https://example.com/runtime)"
    + _SEP
    + "[INBIKU-1032](https://example.com/jira)"
    + _SEP
    + "visto 20/10"
    + _SEP
    + "hecho 20/10: las tres OK"
)


# ── Real examples from the norma (spec verbatim, with canonical separators) ──


class TestParseLineRealExamples:
    """The three canonical examples from the spec must parse correctly."""

    def test_tarea_4parts_open(self):
        result = parse_line(LINE_TAREA_4PARTS)
        assert result is not None
        assert result.closed is False
        assert result.id == "20261019-2015-tayfun-patxi"
        assert result.id_parts.fecha == "20261019"
        assert result.id_parts.hora == "2015"
        assert result.id_parts.remitente == "tayfun"
        assert result.id_parts.destinatario == "patxi"
        assert result.id_parts.b is False
        assert result.tipo == "Tarea"
        assert result.reply_to is None
        assert result.plazo == "23/10"
        assert result.estados == []
        assert result.raw == LINE_TAREA_4PARTS

    def test_respuesta_with_reply_to(self):
        result = parse_line(LINE_RESPUESTA)
        assert result is not None
        assert result.closed is False
        assert result.id == "20261019-2130-patxi-tayfun"
        assert result.id_parts.remitente == "patxi"
        assert result.id_parts.destinatario == "tayfun"
        assert result.tipo == "Respuesta"
        assert result.reply_to == "20261019-2015-tayfun-patxi"
        assert result.plazo is None
        assert result.body == "Visto, lo miro el miércoles"
        assert result.estados == []

    def test_tarea_3parts_closed_with_multiple_estados(self):
        result = parse_line(LINE_TAREA_3PARTS_CLOSED)
        assert result is not None
        assert result.closed is True
        assert result.id == "20261020-1303-miguel"
        assert result.id_parts.remitente == "miguel"
        assert result.id_parts.destinatario is None
        assert result.id_parts.b is False
        assert result.tipo == "Tarea"
        assert result.reply_to is None
        assert result.plazo is None
        assert "visto 20/10" in result.estados
        assert "hecho 20/10: las tres OK" in result.estados
        assert len(result.estados) == 2
        # States must NOT appear in the body
        assert "visto" not in result.body
        assert "hecho" not in result.body
        # Body must contain the links
        assert "[kb-mcp !6](https://example.com/kbmcp)" in result.body
        assert "[INBIKU-1032](https://example.com/jira)" in result.body


# ── ID format variants ────────────────────────────────────────────────────────


class TestParseLineIdVariants:
    def test_id_3_parts_no_destinatario(self):
        line = "- [ ] 20261001-0900-alice" + _DASH + "Hello"
        result = parse_line(line)
        assert result is not None
        assert result.id == "20261001-0900-alice"
        assert result.id_parts.fecha == "20261001"
        assert result.id_parts.hora == "0900"
        assert result.id_parts.remitente == "alice"
        assert result.id_parts.destinatario is None
        assert result.id_parts.b is False

    def test_id_4_parts_with_destinatario(self):
        line = "- [ ] 20261001-0900-alice-bob" + _DASH + "Hello"
        result = parse_line(line)
        assert result is not None
        assert result.id == "20261001-0900-alice-bob"
        assert result.id_parts.remitente == "alice"
        assert result.id_parts.destinatario == "bob"
        assert result.id_parts.b is False

    def test_id_with_b_suffix(self):
        line = "- [ ] 20261001-0900-alice-bob-b" + _DASH + "Second message"
        result = parse_line(line)
        assert result is not None
        assert result.id == "20261001-0900-alice-bob-b"
        assert result.id_parts.remitente == "alice"
        assert result.id_parts.destinatario == "bob"
        assert result.id_parts.b is True

    def test_id_4parts_where_last_is_b_and_no_prior_destinatario_b_is_destinatario(
        self,
    ):
        # MENOR 5: "20261001-0900-alice-b" has only one name before "b"
        # → "b" is the destinatario username, not the -b duplicate suffix.
        # The -b suffix spec requires a destinatario already present before it.
        line = "- [ ] 20261001-0900-alice-b" + _DASH + "Mensaje"
        result = parse_line(line)
        assert result is not None
        assert result.id_parts.remitente == "alice"
        assert result.id_parts.destinatario == "b"
        assert result.id_parts.b is False

    def test_raw_string_preserved_exactly(self):
        # parse_line must return raw == original input, untouched
        result = parse_line(LINE_TAREA_4PARTS)
        assert result is not None
        assert result.raw == LINE_TAREA_4PARTS


# ── Message types ─────────────────────────────────────────────────────────────


class TestParseLineTypes:
    def test_tipo_mensaje(self):
        line = "- [ ] 20261001-0900-alice-bob" + _SEP + "Mensaje" + _DASH + "Un mensaje"
        assert parse_line(line).tipo == "Mensaje"

    def test_tipo_tarea(self):
        line = "- [ ] 20261001-0900-alice-bob" + _SEP + "Tarea" + _DASH + "Una tarea"
        assert parse_line(line).tipo == "Tarea"

    def test_tipo_pendiente(self):
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Pendiente"
            + _DASH
            + "Un pendiente"
        )
        assert parse_line(line).tipo == "Pendiente"

    def test_tipo_respuesta_includes_reply_to(self):
        line = (
            "- [ ] 20261001-0900-bob-alice"
            + _SEP
            + "Respuesta a 20261001-0800-alice-bob"
            + _DASH
            + "OK"
        )
        result = parse_line(line)
        assert result.tipo == "Respuesta"
        assert result.reply_to == "20261001-0800-alice-bob"

    def test_no_tipo_field_returns_none_tipo(self):
        # A line without a tipo field still parses; tipo is None (not an error)
        line = "- [ ] 20261001-0900-alice" + _DASH + "Sin tipo"
        result = parse_line(line)
        assert result is not None
        assert result.tipo is None


# ── Open / closed checkbox ────────────────────────────────────────────────────


class TestParseLineClosed:
    def test_open_checkbox_gives_false(self):
        line = "- [ ] 20261001-0900-alice" + _DASH + "Texto"
        assert parse_line(line).closed is False

    def test_closed_checkbox_gives_true(self):
        line = "- [x] 20261001-0900-alice" + _DASH + "Texto"
        assert parse_line(line).closed is True


# ── Estado detection ──────────────────────────────────────────────────────────


class TestParseLineEstados:
    def test_single_visto(self):
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Hacer algo"
            + _SEP
            + "visto 01/10"
        )
        result = parse_line(line)
        assert result.estados == ["visto 01/10"]
        assert result.body == "Hacer algo"

    def test_single_aceptado(self):
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Algo"
            + _SEP
            + "aceptado → todo"
        )
        result = parse_line(line)
        assert result.estados == ["aceptado → todo"]

    def test_single_hecho(self):
        line = (
            "- [x] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Algo"
            + _SEP
            + "hecho → https://example.com"
        )
        result = parse_line(line)
        assert result.estados == ["hecho → https://example.com"]

    def test_single_rechazado(self):
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Algo"
            + _SEP
            + "rechazado: motivo claro"
        )
        result = parse_line(line)
        assert result.estados == ["rechazado: motivo claro"]

    def test_multiple_estados_ordered(self):
        line = (
            "- [x] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Tarea"
            + _SEP
            + "visto 01/10"
            + _SEP
            + "hecho 02/10: OK"
        )
        result = parse_line(line)
        assert result.estados == ["visto 01/10", "hecho 02/10: OK"]
        assert result.body == "Tarea"

    def test_body_with_sep_chars_is_not_treated_as_estado(self):
        # Body can contain ' · ' — only trailing keyword-matched segments are estados
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "Texto A"
            + _SEP
            + "Texto B"
            + _SEP
            + "visto 01/10"
        )
        result = parse_line(line)
        assert result.estados == ["visto 01/10"]
        assert "Texto A" in result.body
        assert "Texto B" in result.body

    def test_capital_visto_is_not_an_estado(self):
        # Estado detection is case-sensitive; "Visto" is body text, not a state
        line = "- [ ] 20261001-0900-alice" + _DASH + "Visto, lo miro el miércoles"
        result = parse_line(line)
        assert result.estados == []
        assert result.body == "Visto, lo miro el miércoles"

    # ── MAYOR 2: only exact estado forms must be recognized ────────────────────

    def test_body_starting_with_keyword_but_not_valid_estado_form(self):
        # "hecho algo malo" starts with "hecho" but is NOT "hecho → …" or "hecho DD/MM"
        # → it is body text, not an estado; scanning must stop before it.
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "hecho algo malo"
            + _SEP
            + "visto 01/10"
        )
        result = parse_line(line)
        assert result.body == "hecho algo malo"
        assert result.estados == ["visto 01/10"]

    def test_rechazado_without_colon_is_not_estado(self):
        # "rechazado por el cliente" does not match "rechazado: <motivo>" → body text.
        line = (
            "- [ ] 20261001-0900-alice-bob"
            + _SEP
            + "Tarea"
            + _DASH
            + "rechazado por el cliente"
            + _SEP
            + "visto 01/10"
        )
        result = parse_line(line)
        assert result.body == "rechazado por el cliente"
        assert result.estados == ["visto 01/10"]


# ── Non-buzón lines → None ────────────────────────────────────────────────────


class TestParseLineNonBuzon:
    def test_plain_text_returns_none(self):
        assert parse_line("Esto no es una línea de buzón") is None

    def test_empty_string_returns_none(self):
        assert parse_line("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_line("   ") is None

    def test_markdown_header_returns_none(self):
        assert parse_line("# Un título") is None

    def test_regular_checklist_without_id_returns_none(self):
        # A regular markdown task (no buzón ID after the checkbox)
        assert parse_line("- [ ] Una tarea sin formato de buzón") is None

    def test_checkbox_with_garbage_id_returns_none(self):
        # Has checkbox and body sep but no parsable ID
        line = "- [ ] garbage" + _DASH + "blah"
        assert parse_line(line) is None

    def test_never_raises_on_any_input(self):
        # parse_line must NEVER raise, regardless of input
        # (EAFP boundary: caller does not need try/except)
        garbage_inputs = [
            "- [ ] garbage · no · id — blah",
            "- [x]",
            "· · ·",
            "—",
            "- [ ] " + ("x" * 1000),
            "- [ ] 99999999-9999-x — y",
        ]
        for s in garbage_inputs:
            parse_line(s)  # must not raise


# ── build_line ────────────────────────────────────────────────────────────────


class TestBuildLine:
    def test_basic_build_structure(self):
        dt = datetime(2026, 10, 19, 20, 15)
        result = build_line(
            remitente="tayfun",
            destinatario="patxi",
            tipo="Tarea",
            texto="Revisar el MR",
            fecha_hora=dt,
        )
        assert result.startswith("- [ ] ")
        assert "20261019-2015-tayfun-patxi" in result
        assert _SEP + "Tarea" + _DASH in result
        assert "Revisar el MR" in result

    def test_build_always_produces_open_line(self):
        dt = datetime(2026, 10, 19, 20, 15)
        result = build_line("a", "b", "Mensaje", "Texto", dt)
        assert result.startswith("- [ ] ")
        assert "- [x] " not in result

    def test_build_with_plazo(self):
        dt = datetime(2026, 10, 19, 20, 15)
        result = build_line(
            remitente="tayfun",
            destinatario="patxi",
            tipo="Tarea",
            texto="Revisar",
            fecha_hora=dt,
            plazo="23/10",
        )
        assert "plazo 23/10" in result

    def test_build_respuesta_format(self):
        dt = datetime(2026, 10, 19, 21, 30)
        result = build_line(
            remitente="patxi",
            destinatario="tayfun",
            tipo="Respuesta",
            texto="OK",
            fecha_hora=dt,
            reply_to="20261019-2015-tayfun-patxi",
        )
        assert "Respuesta a 20261019-2015-tayfun-patxi" in result
        assert _DASH + "OK" in result
        # "Respuesta" alone should NOT appear without "a <ID>"
        assert _SEP + "Respuesta" + _DASH not in result

    def test_build_with_enlaces(self):
        dt = datetime(2026, 10, 19, 20, 15)
        result = build_line(
            remitente="alice",
            destinatario="bob",
            tipo="Mensaje",
            texto="Ver enlace",
            fecha_hora=dt,
            enlaces=[("MR !7", "https://example.com/mr7")],
        )
        assert "[MR !7](https://example.com/mr7)" in result

    def test_build_with_sufijo_b(self):
        dt = datetime(2026, 10, 19, 20, 15)
        result = build_line(
            remitente="alice",
            destinatario="bob",
            tipo="Mensaje",
            texto="Segundo mensaje",
            fecha_hora=dt,
            sufijo_b=True,
        )
        assert "20261019-2015-alice-bob-b" in result

    def test_build_id_format_uses_datetime(self):
        dt = datetime(2026, 1, 5, 8, 3)
        result = build_line("a", "b", "Mensaje", "X", dt)
        # Zero-padded month, day, hour, minute
        assert "20260105-0803-a-b" in result


# ── Round-trip: build_line → parse_line ──────────────────────────────────────


class TestBuildParseRoundTrip:
    def test_basic_roundtrip(self):
        dt = datetime(2026, 10, 19, 20, 15)
        raw = build_line("tayfun", "patxi", "Tarea", "Revisar el MR", dt)
        parsed = parse_line(raw)
        assert parsed is not None
        assert parsed.closed is False
        assert parsed.id == "20261019-2015-tayfun-patxi"
        assert parsed.tipo == "Tarea"
        assert parsed.body == "Revisar el MR"
        assert parsed.estados == []

    def test_roundtrip_preserves_plazo(self):
        dt = datetime(2026, 10, 19, 20, 15)
        raw = build_line("a", "b", "Tarea", "Texto", dt, plazo="30/10")
        parsed = parse_line(raw)
        assert parsed.plazo == "30/10"

    def test_roundtrip_respuesta(self):
        dt = datetime(2026, 10, 19, 21, 30)
        raw = build_line(
            "patxi",
            "tayfun",
            "Respuesta",
            "Visto",
            dt,
            reply_to="20261019-2015-tayfun-patxi",
        )
        parsed = parse_line(raw)
        assert parsed is not None
        assert parsed.tipo == "Respuesta"
        assert parsed.reply_to == "20261019-2015-tayfun-patxi"

    def test_roundtrip_sufijo_b(self):
        dt = datetime(2026, 10, 1, 9, 0)
        raw = build_line("alice", "bob", "Mensaje", "Segundo", dt, sufijo_b=True)
        parsed = parse_line(raw)
        assert parsed is not None
        assert parsed.id_parts.b is True
        assert parsed.id_parts.remitente == "alice"
        assert parsed.id_parts.destinatario == "bob"

    def test_roundtrip_multiple_enlaces(self):
        dt = datetime(2026, 10, 1, 9, 0)
        enlace_list = [
            ("MR !1", "https://example.com/mr1"),
            ("TICKET-42", "https://example.com/ticket42"),
        ]
        raw = build_line(
            "alice", "bob", "Tarea", "Ver los enlaces", dt, enlaces=enlace_list
        )
        parsed = parse_line(raw)
        assert parsed is not None
        assert "[MR !1](https://example.com/mr1)" in parsed.body
        assert "[TICKET-42](https://example.com/ticket42)" in parsed.body


# ── Transform helpers ─────────────────────────────────────────────────────────


class TestAppendEstado:
    def test_adds_separator_and_estado_at_end(self):
        raw = "- [ ] 20261001-0900-alice-bob" + _SEP + "Tarea" + _DASH + "Hacer algo"
        result = append_estado(raw, "visto 01/10")
        assert result.endswith(_SEP + "visto 01/10")

    def test_preserves_everything_before_estado(self):
        raw = "- [ ] 20261001-0900-alice-bob" + _SEP + "Tarea" + _DASH + "Hacer algo"
        result = append_estado(raw, "visto 01/10")
        assert raw in result  # original line is a prefix of the result

    def test_appended_estado_is_detectable_by_parser(self):
        raw = "- [ ] 20261001-0900-alice-bob" + _SEP + "Tarea" + _DASH + "Hacer algo"
        raw_with_estado = append_estado(raw, "visto 01/10")
        parsed = parse_line(raw_with_estado)
        assert parsed is not None
        assert parsed.estados == ["visto 01/10"]
        assert parsed.body == "Hacer algo"

    def test_append_two_estados_sequentially(self):
        raw = "- [ ] 20261001-0900-alice-bob" + _SEP + "Tarea" + _DASH + "Hacer algo"
        raw = append_estado(raw, "visto 01/10")
        raw = append_estado(raw, "hecho 02/10: OK")
        parsed = parse_line(raw)
        assert parsed.estados == ["visto 01/10", "hecho 02/10: OK"]


class TestSetClosed:
    def test_set_closed_true_changes_checkbox(self):
        raw = "- [ ] 20261001-0900-alice" + _DASH + "Texto"
        result = set_closed(raw, True)
        assert result.startswith("- [x] ")
        assert "- [ ] " not in result

    def test_set_closed_false_changes_checkbox(self):
        raw = "- [x] 20261001-0900-alice" + _DASH + "Texto"
        result = set_closed(raw, False)
        assert result.startswith("- [ ] ")
        assert "- [x] " not in result

    def test_set_closed_true_preserves_rest(self):
        raw = "- [ ] 20261001-0900-alice" + _DASH + "Texto con detalles"
        result = set_closed(raw, True)
        assert "Texto con detalles" in result
        assert result[6:] == raw[6:]  # only checkbox changes

    def test_set_closed_false_preserves_rest(self):
        raw = "- [x] 20261001-0900-alice" + _DASH + "Texto con detalles"
        result = set_closed(raw, False)
        assert "Texto con detalles" in result
        assert result[6:] == raw[6:]  # only checkbox changes

    def test_set_closed_true_is_idempotent(self):
        raw = "- [x] 20261001-0900-alice" + _DASH + "Texto"
        assert set_closed(raw, True) == raw

    def test_set_closed_false_is_idempotent(self):
        raw = "- [ ] 20261001-0900-alice" + _DASH + "Texto"
        assert set_closed(raw, False) == raw

    # ── MAYOR 1: idempotent calls must not corrupt embedded checkboxes ──────────

    def test_set_closed_false_idempotent_does_not_corrupt_embedded_closed_in_body(self):
        # Repro A: line is already open; body contains "- [x] "; set_closed(False)
        # must return the string unchanged, not replace "- [x] " inside the body.
        raw = "- [ ] 20261001-0900-alice" + _DASH + "texto con - [x] embedded"
        result = set_closed(raw, False)
        assert result == raw

    def test_set_closed_true_idempotent_does_not_corrupt_embedded_open_in_body(self):
        # Repro B: line is already closed; body contains "- [ ] "; set_closed(True)
        # must return the string unchanged, not replace "- [ ] " inside the body.
        raw = "- [x] 20261001-0900-alice" + _DASH + "texto con - [ ] embedded"
        result = set_closed(raw, True)
        assert result == raw


# ── extract_id ────────────────────────────────────────────────────────────────


class TestExtractId:
    def test_extracts_from_4part_open_line(self):
        assert extract_id(LINE_TAREA_4PARTS) == "20261019-2015-tayfun-patxi"

    def test_extracts_from_3part_closed_line(self):
        assert extract_id(LINE_TAREA_3PARTS_CLOSED) == "20261020-1303-miguel"

    def test_extracts_from_respuesta_line(self):
        assert extract_id(LINE_RESPUESTA) == "20261019-2130-patxi-tayfun"

    def test_extracts_b_suffix_id(self):
        line = "- [ ] 20261001-0900-alice-bob-b" + _DASH + "Segundo"
        assert extract_id(line) == "20261001-0900-alice-bob-b"

    def test_returns_none_for_non_buzon_line(self):
        assert extract_id("# Un título") is None

    def test_returns_none_for_empty_string(self):
        assert extract_id("") is None

    def test_returns_none_for_regular_checklist(self):
        assert extract_id("- [ ] Una tarea sin ID") is None
