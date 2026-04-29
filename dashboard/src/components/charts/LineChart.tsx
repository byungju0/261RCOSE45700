import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { chartTooltipProps } from './tooltip';

interface LineChartProps {
  data: Array<{ name: string; value: number }>;
  /** CSS color (CSS variable, hex, hsl, oklch). Defaults to --primary token. */
  color?: string;
  height?: number;
}

export function LineChart({
  data,
  color = 'var(--primary)',
  height = 260,
}: LineChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsLineChart
        data={data}
        margin={{ top: 16, right: 16, bottom: 16, left: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" stroke="var(--muted-foreground)" fontSize={12} />
        <YAxis allowDecimals={false} stroke="var(--muted-foreground)" fontSize={12} />
        <Tooltip {...chartTooltipProps} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={{ r: 3, fill: color }}
          activeDot={{ r: 5 }}
        />
      </RechartsLineChart>
    </ResponsiveContainer>
  );
}
