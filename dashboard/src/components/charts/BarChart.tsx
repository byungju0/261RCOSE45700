import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface BarChartProps {
  data: Array<{ name: string; value: number }>;
  /** CSS color (CSS variable, hex, hsl, oklch). Defaults to --foreground token. */
  color?: string;
  height?: number;
}

/**
 * Tracker BarChart — 가로 레이아웃 + 얇은 막대 + 0.85 opacity.
 * UX Spec HTML 시안의 .bar-row 스타일에 가깝게 (label 좌측 / 막대 중앙 / 숫자 우측).
 *
 * 색상은 var(--foreground) 기본 (near-black). Direction C-Light 톤 유지하되
 * fillOpacity로 시각적 강도 완화 → "데이터 막대" 느낌.
 */
export function BarChart({
  data,
  color = 'var(--foreground)',
  height = 260,
}: BarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart
        data={data}
        layout="vertical"
        margin={{ top: 8, right: 32, bottom: 8, left: 8 }}
      >
        <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis
          type="number"
          stroke="var(--muted-foreground)"
          fontSize={11}
          allowDecimals={false}
        />
        <YAxis
          dataKey="name"
          type="category"
          stroke="var(--muted-foreground)"
          fontSize={12}
          width={120}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip cursor={{ fill: 'var(--muted)' }} />
        <Bar
          dataKey="value"
          fill={color}
          fillOpacity={0.85}
          radius={[0, 4, 4, 0]}
          barSize={14}
        >
          <LabelList
            dataKey="value"
            position="right"
            fill="var(--foreground)"
            fontSize={12}
            fontFamily="var(--font-mono)"
          />
        </Bar>
      </RechartsBarChart>
    </ResponsiveContainer>
  );
}
