import { Button } from "@/components/ui/button";

interface Props {
  warnings: string[];
  unresolved: string[];
  downloadUrl?: string;
}

export const PreviewModal = ({ warnings, unresolved, downloadUrl }: Props) => (
  <div className="space-y-2 rounded border p-3 text-sm">
    <div>Warnings: {warnings.length ? warnings.join(", ") : "none"}</div>
    <div>Unresolved: {unresolved.length ? unresolved.join(", ") : "none"}</div>
    {downloadUrl ? (
      <Button asChild size="sm" variant="outline">
        <a href={downloadUrl}>Скачать результат</a>
      </Button>
    ) : null}
  </div>
);
