import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type JsonKpiGridProps = {
  payload: Record<string, unknown> | null;
  loading?: boolean;
};

const normalizeLabel = (key: string) =>
  key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

export const JsonKpiGrid = ({ payload, loading = false }: JsonKpiGridProps) => {
  const entries = Object.entries(payload ?? {});

  if (!entries.length) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          Нет данных для выбранных фильтров.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {entries.map(([key, value]) => (
        <Card key={key}>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">
              {normalizeLabel(key)}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {loading ? "—" : String(value)}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};
