#!/usr/bin/env python3
"""Create compact A/E expression GIFs from the approved visual language.

The resulting GIFs are fed to Espressif's gif_to_aaf.py converter.
"""
from pathlib import Path
import subprocess

OUT = Path("/tmp/orika-emotion-gifs")
OUT.mkdir(parents=True, exist_ok=True)

def svg(pack: str, state: str, phase: int) -> str:
    if pack == "A":
        # Dynamic energy core: irregular gradient-like body, two orbit tracks,
        # and three small sparks. The palette shifts by state and phase.
        palette = {"thinking": ["#ffd166", "#ff8f70", "#9b7bff"], "speaking": ["#638bff", "#83eee0", "#b9fff8"]}.get(state, ["#83eee0", "#638bff", "#a17cff"])
        glow = palette[phase % 3]
        scale = 1.0 + (0.08 if state == "speaking" else (0.05 if phase == 1 else 0))
        angle = phase * 18
        core = (f'<path d="M160 69 C190 68 214 90 210 119 C207 151 185 173 154 171 '
                f'C125 168 105 150 109 120 C112 89 130 72 160 69Z" fill="{glow}" opacity=".9" '
                f'transform="rotate({angle/4} 160 120) scale({scale} 1)" transform-origin="160 120"/>'
                f'<ellipse cx="160" cy="120" rx="70" ry="50" fill="none" stroke="{glow}" stroke-opacity=".35" stroke-width="2" '
                f'transform="rotate({angle} 160 120)"/><ellipse cx="160" cy="120" rx="88" ry="64" fill="none" stroke="#7c9dff55" stroke-width="2" '
                f'transform="rotate({-angle} 160 120)"/>')
        sparks = ''.join(f'<circle cx="{x}" cy="{y}" r="{3 + ((phase+i)%2)}" fill="#e8ffff" opacity="{.45 + .2*((phase+i)%3)}"/>' for i, (x, y) in enumerate(((78, 78), (242, 94), (219, 181))))
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" rx="34" fill="#071522"/><rect x="12" y="12" width="296" height="216" rx="30" fill="#102d42" stroke="#58dfff" stroke-width="5"/>{core}{sparks}</svg>'
    # E: P6 eyes, dark amber display with natural eye motion.
    shift = (-7, 0, 7)[phase % 3] if state == "thinking" else 0
    scale = (1.0, 1.08, .94)[phase % 3] if state == "listening" else 1.0
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" rx="34" fill="#0b0806"/><rect x="12" y="12" width="296" height="216" rx="30" fill="#281207" stroke="#734018" stroke-width="2"/><g transform="translate({shift} 0) scale({scale} 1)" transform-origin="160 120"><ellipse cx="105" cy="120" rx="34" ry="42" fill="#ffb52e"/><ellipse cx="215" cy="120" rx="34" ry="42" fill="#ffb52e"/><circle cx="105" cy="120" r="13" fill="#321304"/><circle cx="215" cy="120" r="13" fill="#321304"/><circle cx="98" cy="110" r="6" fill="#fff7d0"/><circle cx="208" cy="110" r="6" fill="#fff7d0"/></g></svg>'

for pack in ("A", "E"):
    # Each device state gets its own loop.  Concatenating idle/thinking/
    # speaking frames into one GIF makes every state visibly jump when the
    # animation wraps and prevents the firmware from selecting a natural pose.
    for state in ("idle", "listening", "thinking", "executing", "speaking"):
        frames = []
        phases = 4 if state in ("idle", "listening") else 6
        for phase in range(phases):
            path = OUT / f"{pack}_{state}_{phase}.svg"
            path.write_text(svg(pack, state, phase), encoding="utf-8")
            png = path.with_suffix(".png")
            subprocess.run(["convert", str(path), str(png)], check=True)
            frames.append(str(png))
        subprocess.run(["convert", "-delay", "16", "-loop", "0", *frames,
                        str(OUT / f"{pack}_{state}.gif")], check=True)
print(OUT)
