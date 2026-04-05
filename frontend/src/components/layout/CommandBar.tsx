import { Command, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

type CommandItem = {
  id: string;
  title: string;
  path: string;
  keywords: string;
};

const DEFAULT_COMMANDS: CommandItem[] = [
  { id: "dashboard", title: "Рабочий стол", path: "/", keywords: "дашборд главная обзор" },
  { id: "documents", title: "Документы", path: "/documents", keywords: "документы шаблоны пайплайн" },
  { id: "tasks", title: "Задачи", path: "/tasks", keywords: "задачи сроки инбокс" },
  { id: "risks", title: "Риски", path: "/risk", keywords: "риски опасности меры" },
  { id: "training", title: "Обучение", path: "/training", keywords: "обучение инструктажи курсы" },
  { id: "inspections", title: "Проверки", path: "/inspections", keywords: "проверки аудит чеклисты" },
  { id: "incidents", title: "Инциденты", path: "/incidents", keywords: "инциденты нс расследование" },
  { id: "notifications", title: "Уведомления", path: "/notifications", keywords: "уведомления оповещения" },
];

export const CommandBar = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return DEFAULT_COMMANDS;
    return DEFAULT_COMMANDS.filter(
      (item) =>
        item.title.toLowerCase().includes(q) || item.keywords.toLowerCase().includes(q),
    );
  }, [query]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden items-center gap-2 rounded-md border px-3 py-2 text-xs text-muted-foreground hover:bg-muted lg:inline-flex"
        aria-label="Открыть палитру команд"
      >
        <Command className="h-3.5 w-3.5" />
        Команды
        <span className="rounded border px-1.5 py-0.5 text-[10px]">Ctrl+K</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Палитра команд</DialogTitle>
            <DialogDescription>Поиск разделов и быстрый переход по платформе</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти раздел или действие"
                className="pl-9"
              />
            </div>
            <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border p-2">
              {items.map((item) => (
                <Link
                  key={item.id}
                  to={item.path}
                  onClick={() => setOpen(false)}
                  className="block rounded px-2 py-2 text-sm hover:bg-muted"
                >
                  {item.title}
                </Link>
              ))}
              {!items.length && <p className="px-2 py-3 text-sm text-muted-foreground">Ничего не найдено</p>}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
