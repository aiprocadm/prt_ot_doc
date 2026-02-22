import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/api/client";
import { TokenHelp } from "./TokenHelp";
import { PreviewModal } from "./PreviewModal";

export const LayoutPresetEditor = () => {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [headerOdd, setHeaderOdd] = useState("{{company.name}}\n{PAGE}/{NUMPAGES}");
  const [footerOdd, setFooterOdd] = useState("{{doc.title}}");
  const [preview, setPreview] = useState<{ warnings: string[]; unresolved: string[] }>({ warnings: [], unresolved: [] });

  const save = async () => {
    await apiClient.post("/layout-presets", {
      code,
      name,
      header_odd_xml: headerOdd,
      footer_odd_xml: footerOdd,
      different_first: false,
      different_odd_even: false,
      watermark: { enabled: false }
    });
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" />
      </div>
      <Textarea value={headerOdd} onChange={(e) => setHeaderOdd(e.target.value)} placeholder="header odd" />
      <Textarea value={footerOdd} onChange={(e) => setFooterOdd(e.target.value)} placeholder="footer odd" />
      <TokenHelp />
      <div className="flex gap-2">
        <Button onClick={save}>Сохранить пресет</Button>
        <Button variant="outline" onClick={() => setPreview({ warnings: ["Preview endpoint uses apply job"], unresolved: [] })}>Превью</Button>
      </div>
      <PreviewModal warnings={preview.warnings} unresolved={preview.unresolved} />
    </div>
  );
};
