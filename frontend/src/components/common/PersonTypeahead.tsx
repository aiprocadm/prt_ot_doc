import { useEffect, useRef, useState } from "react";

import { searchPersons } from "@/api/personsApi";
import { Input } from "@/components/ui/input";
import type { PersonDto } from "@/types/dto/persons";

export interface PersonOption {
  id: string;
  label: string;
}

interface PersonTypeaheadProps {
  /** Выбранный сотрудник (управляется родителем); null = не выбран. */
  value: PersonOption | null;
  onChange: (person: PersonOption | null) => void;
  placeholder?: string;
  inputId?: string;
}

const personToOption = (p: PersonDto): PersonOption => ({
  id: p.id,
  label: p.full_name || [p.last_name, p.first_name, p.middle_name].filter(Boolean).join(" ") || p.id,
});

const DEBOUNCE_MS = 300;
const MIN_QUERY_LEN = 2;

/**
 * Серверный подбор сотрудника (срез-4): вместо ручного ввода person_id —
 * поиск по ФИО / табельному номеру через GET /persons?q=.
 */
export const PersonTypeahead = ({ value, onChange, placeholder, inputId }: PersonTypeaheadProps) => {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<PersonOption[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastQuery = useRef("");

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const runSearch = (q: string) => {
    lastQuery.current = q;
    setSearching(true);
    searchPersons(q)
      .then((rows) => {
        // отбрасываем ответы устаревших запросов (гонка «медленный старый поверх нового»)
        if (lastQuery.current !== q) return;
        setOptions(rows.map(personToOption));
        setOpen(true);
      })
      .catch(() => {
        if (lastQuery.current !== q) return;
        setOptions([]);
      })
      .finally(() => {
        if (lastQuery.current === q) setSearching(false);
      });
  };

  const handleInput = (raw: string) => {
    setQuery(raw);
    if (value) onChange(null); // ввод сбрасывает прежний выбор
    if (timer.current) clearTimeout(timer.current);
    const q = raw.trim();
    if (q.length < MIN_QUERY_LEN) {
      setOptions([]);
      setOpen(false);
      return;
    }
    timer.current = setTimeout(() => runSearch(q), DEBOUNCE_MS);
  };

  const handlePick = (option: PersonOption) => {
    onChange(option);
    setQuery("");
    setOptions([]);
    setOpen(false);
  };

  return (
    <div className="relative">
      <Input
        id={inputId}
        value={value ? value.label : query}
        onChange={(e) => handleInput(e.target.value)}
        placeholder={placeholder ?? "Поиск по ФИО или таб. номеру"}
        autoComplete="off"
      />
      {open && !value ? (
        <ul
          className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-background shadow-md"
          role="listbox"
        >
          {searching ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">Поиск…</li>
          ) : null}
          {!searching && options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">Никого не найдено</li>
          ) : null}
          {options.map((o) => (
            <li key={o.id} role="option" aria-selected={false}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-muted"
                onClick={() => handlePick(o)}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
