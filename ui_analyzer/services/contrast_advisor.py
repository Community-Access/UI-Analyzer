"""WCAG contrast ratio calculation and color adjustment — ported from ContrastAdvisor.swift."""

from __future__ import annotations

import re
import math
from typing import Optional


# ── WCAG luminance math ───────────────────────────────────────────────────────

def _linearize(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    clean = hex_color.lstrip("#").upper()
    if len(clean) != 6:
        return 0.0
    try:
        value = int(clean, 16)
    except ValueError:
        return 0.0
    r = _linearize(((value >> 16) & 0xFF) / 255)
    g = _linearize(((value >> 8)  & 0xFF) / 255)
    b = _linearize((value         & 0xFF) / 255)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


# ── HSL conversion ────────────────────────────────────────────────────────────

def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    clean = hex_color.lstrip("#").upper()
    try:
        value = int(clean, 16)
    except ValueError:
        return (0.0, 0.0, 0.5)
    r = ((value >> 16) & 0xFF) / 255
    g = ((value >> 8)  & 0xFF) / 255
    b = (value         & 0xFF) / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6 if g < b else 0)) / 6
    elif mx == g:
        h = ((b - r) / d + 2) / 6
    else:
        h = ((r - g) / d + 4) / 6
    return (h, s, l)


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    def hue2rgb(p: float, q: float, t: float) -> float:
        u = t + 1 if t < 0 else (t - 1 if t > 1 else t)
        if u < 1/6: return p + (q - p) * 6 * u
        if u < 1/2: return q
        if u < 2/3: return p + (q - p) * (2/3 - u) * 6
        return p

    if s == 0:
        v = int(round(l * 255))
        return f"#{v:02X}{v:02X}{v:02X}"
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = int(round(hue2rgb(p, q, h + 1/3) * 255))
    g = int(round(hue2rgb(p, q, h)       * 255))
    b = int(round(hue2rgb(p, q, h - 1/3) * 255))
    return f"#{min(255, max(0, r)):02X}{min(255, max(0, g)):02X}{min(255, max(0, b)):02X}"


# ── Color adjustment (binary search in HSL space) ─────────────────────────────

def adjusted_color(fg: str, bg: str, target: float = 4.5) -> Optional[str]:
    bg_lum = relative_luminance(bg)
    h, s, l = _hex_to_hsl(fg)
    should_darken = bg_lum > 0.18
    lo = 0.0 if should_darken else l
    hi = l   if should_darken else 1.0

    for _ in range(30):
        mid = (lo + hi) / 2
        candidate = _hsl_to_hex(h, s, mid)
        ratio = contrast_ratio(candidate, bg)
        if ratio >= target:
            if should_darken: lo = mid
            else:             hi = mid
        else:
            if should_darken: hi = mid
            else:             lo = mid

    trial_l = lo if should_darken else hi
    result = _hsl_to_hex(h, s, trial_l)
    if contrast_ratio(result, bg) >= target and result.upper() != fg.upper():
        return result
    return None


# ── Color extraction from source code ─────────────────────────────────────────

def extract_hex_colors(source: str) -> list[str]:
    found: set[str] = set()
    for match in re.finditer(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b', source):
        hex_val = match.group(0).upper()
        if len(hex_val) == 4:
            c = list(hex_val[1:])
            hex_val = f"#{c[0]}{c[0]}{c[1]}{c[1]}{c[2]}{c[2]}"
        if hex_val not in ("#000000", "#FFFFFF"):
            found.add(hex_val)
    return list(found)


def extract_rgb_colors(source: str) -> list[str]:
    """Extract Color(red: R, green: G, blue: B) Swift literals and rgb(R,G,B) CSS."""
    found: set[str] = set()
    # Swift: Color(red: 0.97, green: 0.42, blue: 0.08)
    for m in re.finditer(
        r'Color\s*\(\s*red:\s*([\d.]+)\s*,\s*green:\s*([\d.]+)\s*,\s*blue:\s*([\d.]+)',
        source
    ):
        r, g, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
        found.add(f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}")
    # CSS: rgb(255, 128, 0) or rgba(255, 128, 0, 1)
    for m in re.finditer(
        r'rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
        source
    ):
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        found.add(f"#{min(255,r):02X}{min(255,g):02X}{min(255,b):02X}")
    return list(found)


# ── Main entry point ──────────────────────────────────────────────────────────

BACKGROUNDS = [
    ("#FFFFFF", "white / light bg"),
    ("#1C1C1E", "dark bg"),
    ("#000000", "black"),
]


def contrast_report(source: str) -> Optional[str]:
    """Return a formatted contrast report string for injection into the AI prompt,
    or None if no colors found or all pass AA."""
    colors = list(set(extract_hex_colors(source) + extract_rgb_colors(source)))
    if not colors:
        return None

    findings: list[str] = []
    for fg in sorted(colors):
        for bg_hex, bg_name in BACKGROUNDS:
            ratio = contrast_ratio(fg, bg_hex)
            if ratio >= 4.5:
                continue
            if ratio < 3.0:
                level = "fails large text (need 3:1)"
            else:
                level = "passes large text but fails normal text (need 4.5:1)"
            line = f"• {fg} on {bg_name}: ratio {ratio:.1f}:1 — {level}"
            alt = adjusted_color(fg, bg_hex, 4.5)
            if alt:
                new_ratio = contrast_ratio(alt, bg_hex)
                line += f"\n  ↳ Suggested alternative: {alt} (ratio {new_ratio:.1f}:1 — passes AA)"
            findings.append(line)

    if not findings:
        return None

    return (
        "AUTOMATED WCAG CONTRAST ANALYSIS (computed from colors in source):\n"
        + "\n".join(findings)
        + "\nUse these exact ratios and suggested alternatives in the Accessibility section."
    )
