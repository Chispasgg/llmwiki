"""Tests unitarios para api/services/okf/config.py."""

import pytest

from services.okf.config import load_okf_config


def test_loads_mapping_and_vocab():
    """load_okf_config() lee correctamente el YAML y construye OkfConfig."""
    cfg = load_okf_config()

    assert cfg.okf_version == "0.2"
    assert cfg.default_type == "Concepto"
    assert "Entidad" in cfg.vocabulary

    # Debe existir una tupla cuyo patrón sea "entities/" y cuyo tipo sea "Entidad"
    entities_entry = next(
        (entry for entry in cfg.section_map if entry[0] == "entities/"), None
    )
    assert entities_entry is not None, (
        'No se encontró ninguna entrada con patrón "entities/" en section_map'
    )
    assert entities_entry[1] == "Entidad"


def test_section_map_is_ordered_tuples():
    """section_map contiene tuplas (str, str) y el orden del YAML se preserva."""
    cfg = load_okf_config()

    # Cada elemento es una tupla de dos strings
    for entry in cfg.section_map:
        assert isinstance(entry, tuple), f"Esperaba tuple, obtuve {type(entry)}"
        assert len(entry) == 2
        assert isinstance(entry[0], str)
        assert isinstance(entry[1], str)

    # El orden se preserva respecto al YAML:
    # "overview" debe aparecer antes que "entities/" que debe aparecer antes que "normas"
    patterns = [entry[0] for entry in cfg.section_map]
    assert patterns.index("overview") < patterns.index("entities/"), (
        '"overview" debe preceder a "entities/" en section_map'
    )
    assert patterns.index("entities/") < patterns.index("normas"), (
        '"entities/" debe preceder a "normas" en section_map'
    )


def test_load_nonexistent_raises_file_not_found():
    """load_okf_config con ruta inexistente lanza FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_okf_config("/ruta/inexistente.yaml")


def test_load_yaml_missing_field_raises_key_error(tmp_path):
    """YAML sin campo obligatorio lanza KeyError."""
    incomplete = tmp_path / "incomplete.yaml"
    incomplete.write_text("okf_version: '0.2'\n# sin otros campos obligatorios\n")
    with pytest.raises(KeyError):
        load_okf_config(str(incomplete))
