/**
 * Birdle AI — theme tokens, ported from the design's app/theme.js.
 * buildVars(t) returns a CSS-custom-property map applied via inline style.
 */
import type { CSSProperties } from 'react';

export type PaletteKey = 'green' | 'earth' | 'slate';
export type PanelKey = 'glass' | 'solid' | 'outline';
export type FontKey = 'editorial' | 'literary' | 'grotesk';

export interface ThemeChoice {
  palette: PaletteKey;
  panel: PanelKey;
  font: FontKey;
  /** Photo presence 0–100; lower = more veil over the photo. */
  photo: number;
}

/** Production defaults (Botanical Green per design). */
export const DEFAULT_THEME: ThemeChoice = {
  palette: 'green',
  panel: 'glass',
  font: 'editorial',
  photo: 62,
};

type Vars = Record<string, string>;

const SHARED: Vars = {
  '--font-body': "'Hanken Grotesk', system-ui, sans-serif",
  '--font-mono': "'Spline Sans Mono', ui-monospace, monospace",
  '--hairline': 'rgba(45,45,32,0.08)',
  '--hairline-strong': 'rgba(45,45,32,0.15)',
};

export const PALETTES: Record<PaletteKey, Vars & { label: string }> = {
  green: {
    label: 'Botanical Green',
    '--accent': 'oklch(0.50 0.072 152)',
    '--accent-strong': 'oklch(0.40 0.058 152)',
    '--accent-ink': 'oklch(0.975 0.012 150)',
    '--accent-shadow': 'oklch(0.42 0.07 152 / 0.55)',
    '--ink': 'oklch(0.255 0.018 152)',
    '--ink-soft': 'oklch(0.43 0.016 152)',
    '--ink-faint': 'oklch(0.60 0.012 152)',
    '--photo-tint': '#163a2a',
    '--photo-blend': 'soft-light',
    '--scrim': 'oklch(0.26 0.03 150)',
  },
  earth: {
    label: 'Warm Earth',
    '--accent': 'oklch(0.555 0.105 52)',
    '--accent-strong': 'oklch(0.45 0.09 48)',
    '--accent-ink': 'oklch(0.985 0.01 80)',
    '--accent-shadow': 'oklch(0.48 0.10 50 / 0.55)',
    '--ink': 'oklch(0.28 0.022 55)',
    '--ink-soft': 'oklch(0.45 0.02 55)',
    '--ink-faint': 'oklch(0.62 0.015 55)',
    '--photo-tint': '#3a2415',
    '--photo-blend': 'soft-light',
    '--scrim': 'oklch(0.27 0.035 50)',
  },
  slate: {
    label: 'Slate & Sky',
    '--accent': 'oklch(0.50 0.062 248)',
    '--accent-strong': 'oklch(0.41 0.052 248)',
    '--accent-ink': 'oklch(0.985 0.006 250)',
    '--accent-shadow': 'oklch(0.42 0.06 248 / 0.55)',
    '--ink': 'oklch(0.27 0.018 250)',
    '--ink-soft': 'oklch(0.44 0.016 250)',
    '--ink-faint': 'oklch(0.61 0.012 250)',
    '--photo-tint': '#1a2438',
    '--photo-blend': 'soft-light',
    '--scrim': 'oklch(0.27 0.028 255)',
  },
};

const PANELS: Record<PanelKey, Vars> = {
  glass: {
    '--panel-bg': 'rgba(252,252,249,0.60)',
    '--panel-blur': 'blur(22px) saturate(1.35)',
    '--panel-border': '1px solid rgba(255,255,255,0.5)',
    '--panel-shadow': '0 20px 54px -24px rgba(18,22,16,0.62)',
    '--input-bg': 'rgba(255,255,255,0.56)',
    '--card-bg': 'rgba(255,255,255,0.5)',
    '--card-border': '1px solid rgba(255,255,255,0.55)',
  },
  solid: {
    '--panel-bg': 'rgba(250,250,247,0.975)',
    '--panel-blur': 'blur(2px)',
    '--panel-border': '1px solid rgba(40,40,30,0.06)',
    '--panel-shadow': '0 20px 54px -26px rgba(18,22,16,0.6)',
    '--input-bg': '#ffffff',
    '--card-bg': '#ffffff',
    '--card-border': '1px solid rgba(40,40,30,0.08)',
  },
  outline: {
    '--panel-bg': 'rgba(252,252,249,0.32)',
    '--panel-blur': 'blur(16px) saturate(1.2)',
    '--panel-border': '1.5px solid rgba(255,255,255,0.7)',
    '--panel-shadow': '0 12px 40px -28px rgba(18,22,16,0.5)',
    '--input-bg': 'rgba(255,255,255,0.42)',
    '--card-bg': 'rgba(255,255,255,0.30)',
    '--card-border': '1.5px solid rgba(255,255,255,0.6)',
  },
};

const FONTS: Record<FontKey, { label: string; family: string; weight: number }> = {
  editorial: { label: 'Editorial', family: "'Newsreader', Georgia, serif", weight: 540 },
  literary: { label: 'Literary', family: "'Spectral', Georgia, serif", weight: 500 },
  grotesk: { label: 'Grotesk', family: "'Space Grotesk', sans-serif", weight: 600 },
};

/** Build the CSS-variable style object for a theme choice. */
export function buildVars(t: ThemeChoice): CSSProperties {
  const pal = PALETTES[t.palette] || PALETTES.green;
  const panel = PANELS[t.panel] || PANELS.glass;
  const font = FONTS[t.font] || FONTS.editorial;
  const prom = typeof t.photo === 'number' ? t.photo : 62;
  const veil = Math.max(0, Math.min(0.5, ((100 - prom) / 100) * 0.55));
  const { label: _palLabel, ...palVars } = pal;
  return {
    ...SHARED,
    ...palVars,
    ...panel,
    '--font-display': font.family,
    '--display-weight': String(font.weight),
    '--veil-opacity': String(veil),
  } as CSSProperties;
}
