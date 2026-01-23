import { useEffect } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { FileTable } from "@/features/files/FileTable";
import { FileUploader } from "@/features/files/FileUploader";
import { useFilesStore } from "@/stores/files";

const FilesPage = () => {
  const { list } = useFilesStore();

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Файлы" }]} />
      <FileUploader />
      <Card>
        <CardContent className="py-6">
          <FileTable />
        </CardContent>
      </Card>
    </div>
  );
};

export default FilesPage;
