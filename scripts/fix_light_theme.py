"""Scope light/dark CSS so light theme works cabinet-wide."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "app" / "static" / "css" / "cabinet-theme.css"
STYLE_CSS = ROOT / "app" / "static" / "css" / "style.css"
REFINE_CSS = ROOT / "app" / "static" / "css" / "cabinet-refine.css"


def scope_cabinet_theme_light():
    lines = THEME_CSS.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    in_light = False
    for i, line in enumerate(lines):
        if i == 6:  # line 7 — start of rules after header comment
            in_light = True
        if "Professional Dark Cabinet" in line:
            in_light = False
        if in_light and "html:has(.app-container)" in line and 'data-theme="light"' not in line:
            line = line.replace(
                "html:has(.app-container)",
                'html[data-theme="light"]:has(.app-container)',
            )
        out.append(line)
    THEME_CSS.write_text("".join(out), encoding="utf-8")
    print("Scoped light rules in cabinet-theme.css (lines 7-621)")


def scope_style_dark():
    text = STYLE_CSS.read_text(encoding="utf-8")
    prefix = 'html[data-theme="dark"] '
    # Universal button fallback — was .dark-theme button (matches html.dark-theme)
    text = text.replace(
        "/* Universal button fallback (requested) */\n.dark-theme button,\n.dark-theme [role=\"button\"],\n.dark-theme .btn {",
        "/* Universal button fallback (requested) */\nhtml[data-theme=\"dark\"] button,\nhtml[data-theme=\"dark\"] [role=\"button\"],\nhtml[data-theme=\"dark\"] .btn {",
    )
    if prefix + "body.dark-theme" not in text:
        text = text.replace("body.dark-theme", prefix + "body.dark-theme")
    STYLE_CSS.write_text(text, encoding="utf-8")
    print("Scoped body.dark-theme rules in style.css")


def scope_refine_palette():
    text = REFINE_CSS.read_text(encoding="utf-8")
    old = 'html[data-cabinet-skin="refine"]:has(.app-container) {\n    --bg-primary: #f4f6f8;'
    new = 'html[data-theme="light"][data-cabinet-skin="refine"]:has(.app-container) {\n    --bg-primary: #f4f6f8;'
    if old in text:
        text = text.replace(old, new, 1)
        REFINE_CSS.write_text(text, encoding="utf-8")
        print("Scoped refine light palette to data-theme=light")
    else:
        print("Refine palette already scoped or not found")


def scope_style_cabinet_vars():
    text = STYLE_CSS.read_text(encoding="utf-8")
    old = "html:has(.app-container) {\n    /* Мягкий сине-серый фон"
    new = 'html[data-theme="light"]:has(.app-container) {\n    /* Мягкий сине-серый фон'
    if old in text:
        text = text.replace(old, new, 1)
        STYLE_CSS.write_text(text, encoding="utf-8")
        print("Scoped style.css cabinet vars to light theme only")


if __name__ == "__main__":
    scope_cabinet_theme_light()
    scope_style_dark()
    scope_refine_palette()
    scope_style_cabinet_vars()
