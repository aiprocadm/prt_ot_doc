import type { ReplaceDiffItem } from "@/api/documents";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export const ReplaceDiffViewer = ({
  items,
  summary
}: {
  items: ReplaceDiffItem[];
  summary?: { matches?: number; pairs?: Record<string, number> };
}) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Предпросмотр замен</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-sm text-muted-foreground">Совпадений: {summary?.matches ?? items.reduce((acc, item) => acc + item.match_count, 0)}</div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>из</TableHead>
              <TableHead>в</TableHead>
              <TableHead>совпадений</TableHead>
              <TableHead>до</TableHead>
              <TableHead>после</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item, idx) => (
              <TableRow key={`${item.location}-${idx}`}>
                <TableCell className="font-mono text-xs">{item.from}</TableCell>
                <TableCell className="font-mono text-xs">{item.to}</TableCell>
                <TableCell>{item.match_count}</TableCell>
                <TableCell className="max-w-[280px] whitespace-pre-wrap text-xs">{item.before}</TableCell>
                <TableCell className="max-w-[280px] whitespace-pre-wrap text-xs">{item.after}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};
