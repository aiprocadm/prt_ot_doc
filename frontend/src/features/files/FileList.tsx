import { useEffect, useState } from "react";

import { getDownloadUrl, listEntityFiles } from "@/api/files";

type Props = {
  entityType: string;
  entityId: string;
};

export const FileList = ({ entityType, entityId }: Props) => {
  const [items, setItems] = useState<
    Array<{
      file_id: string;
      role: string;
      status: string;
      display_name: string;
      size: number;
    }>
  >([]);

  useEffect(() => {
    listEntityFiles(entityType, entityId)
      .then(setItems)
      .catch(() => setItems([]));
  }, [entityId, entityType]);

  return (
    <div className="space-y-2 text-xs">
      {items.map((item) => (
        <div
          key={item.file_id}
          className="flex items-center justify-between rounded border px-2 py-1"
        >
          <div>
            <div>{item.display_name}</div>
            <div className="text-muted-foreground">
              {item.role} · {item.status} · {item.size} bytes
            </div>
          </div>
          <button
            className="rounded border px-2 py-1"
            disabled={item.status !== "ready"}
            onClick={async () => {
              const url = await getDownloadUrl(item.file_id, "ui_preview");
              window.open(url, "_blank", "noopener,noreferrer");
            }}
          >
            Скачать
          </button>
        </div>
      ))}
      {!items.length ? (
        <div className="text-muted-foreground">Файлы отсутствуют</div>
      ) : null}
    </div>
  );
};
