"""
Generate static EB Garamond instances from variable fonts with correct
Windows-compatibility family naming so that XeTeX/fontspec resolves:
  BoldFont={EB Garamond Bold}   ->  Name ID 1 = "EB Garamond Bold"
  ItalicFont={EB Garamond}      ->  Name ID 1 = "EB Garamond", style=Italic

Static instances are required because variable font named instances may not
be correctly selected by XeTeX's fontconfig integration.
"""

import sys

sys.path.insert(0, "/tmp/ft")

from fontTools import ttLib
from fontTools.varLib.instancer import instantiateVariableFont


def make(src: str, wght: int, family: str, style: str, dest: str) -> None:
    tt = ttLib.TTFont(src)
    instantiateVariableFont(tt, {"wght": wght}, inplace=True, optimize=True)

    n = tt["name"]
    for nid in [1, 2, 4, 6, 16, 17]:
        n.removeNames(nameID=nid)

    full = family if style == "Regular" else f"{family} {style}"
    ps = family.replace(" ", "") + ("-" + style if style != "Regular" else "")

    for plat, enc, lang in [(1, 0, 0), (3, 1, 0x0409)]:
        n.setName(family, 1, plat, enc, lang)
        n.setName(style, 2, plat, enc, lang)
        n.setName(full, 4, plat, enc, lang)
        n.setName(ps, 6, plat, enc, lang)

    tt.save(dest)
    print(f"Saved {dest}")


OUT = "/usr/share/fonts/truetype/eb-garamond-gf"
UP = "/tmp/ebg/upright.ttf"
IT = "/tmp/ebg/italic.ttf"

make(UP, 400, "EB Garamond", "Regular", f"{OUT}/EBGaramond-Regular.ttf")
make(UP, 700, "EB Garamond Bold", "Regular", f"{OUT}/EBGaramond-Bold.ttf")
make(IT, 400, "EB Garamond", "Italic", f"{OUT}/EBGaramond-Italic.ttf")
make(IT, 700, "EB Garamond Bold", "Italic", f"{OUT}/EBGaramond-BoldItalic.ttf")
