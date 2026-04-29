/**
 * Recharts `<Tooltip>` 공유 props — 라이트/다크 모두 카드 톤 고정.
 * BarChart / PieChart / LineChart 모두 같은 모양으로 노출.
 */
export const chartTooltipProps = {
  cursor: { fill: 'var(--muted)' as string },
  contentStyle: {
    background: 'var(--card)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    color: 'var(--foreground)',
    fontSize: 12,
  },
  labelStyle: { color: 'var(--foreground)' },
} as const;
