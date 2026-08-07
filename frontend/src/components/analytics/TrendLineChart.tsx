import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  date: string; // ISO
  value: number;
}

interface TrendLineChartProps {
  title: string;
  series: TrendPoint[];
  height?: number;
}

const shortDate = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
};

/** Линейный график одного тренда (12 точек /analytics/trends/*). jsdom не даёт
 * размеров контейнеру — тесты проверяют заголовок/наличие контейнера, не SVG. */
export function TrendLineChart({
  title,
  series,
  height = 220,
}: TrendLineChartProps) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="mb-2 text-sm font-medium">{title}</p>
      {series.length === 0 ? (
        <p className="text-sm text-muted-foreground">Нет данных за период</p>
      ) : (
        <div data-testid={`trend-chart-${title}`} style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={series}
              margin={{ top: 4, right: 8, bottom: 0, left: -16 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" tickFormatter={shortDate} fontSize={11} />
              <YAxis allowDecimals={false} fontSize={11} />
              <Tooltip
                labelFormatter={(label) => shortDate(String(label))}
                formatter={(value) => [String(value), "Значение"]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
