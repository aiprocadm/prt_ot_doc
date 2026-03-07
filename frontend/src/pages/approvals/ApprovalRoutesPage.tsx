import { FormEvent, useEffect, useState } from "react";

import { approvalsApi, type ApprovalRoute } from "@/api/approvals";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const ApprovalRoutesPage = () => {
  const [items, setItems] = useState<ApprovalRoute[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    code: "",
    name: "",
    description: "",
    applies_to: "both"
  });

  const load = async () => {
    setLoading(true);
    try {
      setItems(await approvalsApi.listRoutes());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.code || !form.name) return;
    setSubmitting(true);
    try {
      await approvalsApi.createRoute({
        code: form.code,
        name: form.name,
        description: form.description || null,
        applies_to: form.applies_to,
        conditions_json: {},
        is_default: false,
        status: "active"
      });
      setForm({ code: "", name: "", description: "", applies_to: "both" });
      await load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Маршруты согласования</h1>

      <form className="grid gap-3 rounded border p-4 md:grid-cols-2" onSubmit={onCreate}>
        <Input placeholder="Код маршрута" value={form.code} onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value }))} />
        <Input placeholder="Название" value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} />
        <Input
          placeholder="Область применения: document | pack | both"
          value={form.applies_to}
          onChange={(e) => setForm((prev) => ({ ...prev, applies_to: e.target.value }))}
        />
        <div className="md:col-span-2">
          <Textarea
            placeholder="Описание"
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          />
        </div>
        <div className="md:col-span-2">
          <Button disabled={submitting} type="submit">
            {submitting ? "Сохранение..." : "Создать маршрут"}
          </Button>
        </div>
      </form>

      {loading && <div className="text-sm text-muted-foreground">Загрузка...</div>}

      <div className="space-y-2">
        {items.map((route) => (
          <div key={route.id} className="rounded border p-3 text-sm">
            <div className="font-medium">{route.name}</div>
            <div className="text-muted-foreground">{route.code} • applies_to={route.applies_to} • status={route.status}</div>
            {route.description && <div className="mt-1 text-muted-foreground">{route.description}</div>}
          </div>
        ))}
        {!loading && items.length === 0 && <div className="text-sm text-muted-foreground">Маршрутов пока нет</div>}
      </div>
    </div>
  );
};

export default ApprovalRoutesPage;
