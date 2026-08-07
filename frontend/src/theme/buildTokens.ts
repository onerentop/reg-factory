import type { Palette } from './palette'

type RGB = { r: number; g: number; b: number }

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '')
  const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const int = parseInt(n, 16)
  return { r: (int >> 16) & 255, g: (int >> 8) & 255, b: int & 255 }
}

function toHex({ r, g, b }: RGB): string {
  const h = (v: number) =>
    Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')
  return `#${h(r)}${h(g)}${h(b)}`
}

/** 把 color 朝 target 线性混合 amount(0..1)。 */
function mix(color: string, target: string, amount: number): string {
  const a = hexToRgb(color)
  const b = hexToRgb(target)
  return toHex({
    r: a.r + (b.r - a.r) * amount,
    g: a.g + (b.g - a.g) * amount,
    b: a.b + (b.b - a.b) * amount,
  })
}

/** 生成 rgba() 字符串。 */
function rgba(hex: string, alpha: number): string {
  const { r, g, b } = hexToRgb(hex)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const WHITE = '#ffffff'
const BLACK = '#000000'

/**
 * Factory + Strategy：核心调色板 → 完整 CSS 变量集。
 * 明/暗按 mode 选不同的派生方向（亮色朝黑混、暗色朝白混）。
 * 注意：字体、阴影、--radius-lg 主题无关，固定在 global.css :root，不在此派生。
 */
export function buildCssVars(p: Palette): Record<string, string> {
  const dark = p.mode === 'dark'
  const softAlpha = dark ? 0.16 : 0.1

  return {
    '--bg-primary': p.bg,
    '--bg-card': p.card,
    '--bg-card-hover': dark ? mix(p.card, WHITE, 0.04) : mix(p.card, p.text, 0.02),
    '--bg-sidebar': p.sidebar,
    '--bg-sidebar-icon': p.sidebarIcon,
    '--bg-input': dark ? mix(p.card, BLACK, 0.12) : p.bg,
    '--bg-elevated': dark ? mix(p.card, WHITE, 0.06) : mix(p.bg, p.text, 0.05),
    '--bg-accent-soft': rgba(p.accent, dark ? 0.16 : 0.1),
    '--bg-success-soft': rgba(p.success, softAlpha),
    '--bg-error-soft': rgba(p.error, softAlpha),
    '--bg-warning-soft': rgba(p.warning, softAlpha),

    '--text-primary': p.text,
    '--text-secondary': p.textSecondary,
    '--text-muted': mix(p.textSecondary, p.bg, 0.35),
    '--text-bright': dark ? mix(p.text, WHITE, 0.15) : mix(p.text, BLACK, 0.2),

    '--border': p.border,
    '--border-bright': dark ? mix(p.border, WHITE, 0.18) : mix(p.border, p.text, 0.22),

    '--accent': p.accent,
    '--accent-light': mix(p.accent, WHITE, dark ? 0.14 : 0.16),
    '--accent-dim': rgba(p.accent, 0.08),
    '--accent-soft': rgba(p.accent, dark ? 0.16 : 0.12),

    '--success': p.success,
    '--success-dim': rgba(p.success, 0.08),
    '--error': p.error,
    '--error-dim': rgba(p.error, 0.08),
    '--warning': p.warning,
    '--warning-dim': rgba(p.warning, 0.08),

    '--radius': p.radius,
  }
}
