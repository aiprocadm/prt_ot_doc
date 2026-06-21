import { Button } from "@/components/ui/button";

interface Props {
  onDownload: (fmt: "docx" | "pdf") => void;
}

export const PrintButtons = ({ onDownload }: Props) => (
  <div className="flex gap-2">
    <Button size="sm" variant="outline" onClick={() => onDownload("docx")}>
      Скачать DOCX
    </Button>
    <Button size="sm" variant="outline" onClick={() => onDownload("pdf")}>
      Скачать PDF
    </Button>
  </div>
);
