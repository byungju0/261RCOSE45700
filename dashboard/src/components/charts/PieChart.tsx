import {
  Cell,
  Legend,
  Pie,
  PieChart as RechartsPieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { CHART_PALETTE_VARS } from './colors';

interface PieChartProps {
  data: Array<{ name: string; value: number }>;
  /** Optional override for slice colors. Defaults to CHART_PALETTE_VARS. */
  colors?: readonly string[];
  height?: number;
  /** Show as donut (innerRadius > 0). Default true to match UX Spec mockup. */
  donut?: boolean;
}

/**
 * Tracker PieChart — 도넛 스타일 + 우측 세로 legend (UX Spec HTML 시안 일치).
 * 슬라이스 색상은 var(--chart-1)~var(--chart-5) (UX Spec Step 8 chart palette).
 */
export function PieChart({
  data,
  colors = CHART_PALETTE_VARS,
  height = 260,
  donut = true,
}: PieChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsPieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="40%"
          cy="50%"
          innerRadius={donut ? 50 : 0}
          outerRadius={90}
          paddingAngle={1}
          stroke="var(--background)"
          strokeWidth={2}
        >
          {data.map((entry, idx) => (
            <Cell key={entry.name} fill={colors[idx % colors.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            fontSize: 12,
          }}
        />
        <Legend
          layout="vertical"
          verticalAlign="middle"
          align="right"
          iconType="square"
          wrapperStyle={{
            fontSize: 12,
            paddingLeft: 16,
          }}
        />
      </RechartsPieChart>
    </ResponsiveContainer>
  );
}
