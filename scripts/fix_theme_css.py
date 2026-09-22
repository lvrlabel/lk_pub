"""Scope unconditional dark rules in cabinet-theme.css to [data-theme=\"dark\"]."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'css' / 'cabinet-theme.css'
lines = p.read_text(encoding='utf-8').splitlines()

start = next(i for i, line in enumerate(lines) if 'Professional Dark Cabinet' in line)
end = next(i for i, line in enumerate(lines) if 'GLOBAL DARK OVERRIDE (final)' in line)

for i in range(start, end):
    line = lines[i]
    if 'data-theme="dark"' in line:
        continue
    line = line.replace(
        'html:has(.app-container)[data-accent="blue"]',
        'html[data-theme="dark"]:has(.app-container)[data-accent="blue"]',
    )
    line = line.replace(
        'html:has(.app-container)',
        'html[data-theme="dark"]:has(.app-container)',
    )
    lines[i] = line

fallback_start = next(i for i, line in enumerate(lines) if 'Hard fallback without :has()' in line)
for i in range(fallback_start, end):
    if 'data-theme="dark"' in lines[i]:
        continue
    if 'html[data-accent="blue"]' in lines[i]:
        lines[i] = lines[i].replace(
            'html[data-accent="blue"]',
            'html[data-theme="dark"][data-accent="blue"]',
        )

p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Scoped dark rules in cabinet-theme.css (lines {start + 1}-{end})')
