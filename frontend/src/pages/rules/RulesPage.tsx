import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { isFeatureDisabledError, rulesApi } from "@/api/rules";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { DryRunPanel } from "@/features/rules/DryRunPanel";
import { RuleLibraryPanel } from "@/features/rules/RuleLibraryPanel";
import { RuleFormDialog } from "@/features/rules/RuleFormDialog";
import { TriggerLogPanel } from "@/features/rules/TriggerLogPanel";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import { ACTION_LABELS, eventLabel } from "@/pages/rules/rulesVocab";
import type {
  AutomationRuleRead,
  EventTypeMeta,
  RuleLibraryPage,
} from "@/types/dto/rules";

const conditionsLabel = (count: number): string => {
  if (count === 0) return "все события";
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} условие`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14))
    return `${count} условия`;
  return `${count} условий`;
};

const RulesPage = () => {
  const rulesLoader = useCallback(
    () => rulesApi.list().then((page) => page.items),
    [],
  );
  const eventTypesLoader = useCallback(
    () => rulesApi.eventTypes().then((page) => page.items),
    [],
  );
  const libraryLoader = useCallback(() => rulesApi.library(), []);

  const rulesRes = useAsyncResource<AutomationRuleRead[]>({
    loader: rulesLoader,
    initialData: [],
    errorMessage: "Не удалось загрузить правила автоматизации",
  });
  const eventTypesRes = useAsyncResource<EventTypeMeta[]>({
    loader: eventTypesLoader,
    initialData: [],
    errorMessage: "Не удалось загрузить каталог событий",
  });
  // Библиотека грузится отдельно и её ошибка НЕ гасит экран: правила арендатора
  // важнее справки о том, что поставляется из коробки.
  const libraryRes = useAsyncResource<RuleLibraryPage | null>({
    loader: libraryLoader,
    initialData: null,
    errorMessage: "Не удалось загрузить библиотеку правил",
  });

  const registry = useLocalRegistry({
    items: rulesRes.data,
    match: (rule, query) =>
      [
        rule.name,
        rule.description,
        rule.event_type,
        eventLabel(rule.event_type),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const reloadRules = () => void rulesRes.reload().catch(() => undefined);
  // Выдача библиотеки меняет и реестр правил, и счётчик «выдано N из M».
  const reloadAfterInstall = () => {
    reloadRules();
    void libraryRes.reload().catch(() => undefined);
  };

  const toggleRule = async (rule: AutomationRuleRead, next: boolean) => {
    try {
      await rulesApi.update(rule.id, { is_enabled: next });
      toast.success(next ? "Правило включено" : "Правило выключено");
      await rulesRes.reload();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const runTest = async (rule: AutomationRuleRead) => {
    try {
      const result = await rulesApi.test(rule.id, {});
      toast.success(
        `Совпадений ${result.matched_count} из ${result.events_checked}`,
      );
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const removeRule = async (rule: AutomationRuleRead) => {
    if (!window.confirm(`Удалить правило «${rule.name}»?`)) return;
    try {
      await rulesApi.remove(rule.id);
      toast.success("Правило удалено");
      await rulesRes.reload();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const columns: ColumnDef<AutomationRuleRead, unknown>[] = [
    {
      accessorKey: "name",
      header: "Имя",
      cell: ({ row }) => (
        <span className="font-medium">{row.original.name}</span>
      ),
    },
    {
      accessorKey: "event_type",
      header: "Событие",
      cell: ({ row }) => eventLabel(row.original.event_type),
    },
    {
      id: "conditions",
      header: "Условия",
      cell: ({ row }) =>
        conditionsLabel(row.original.conditions_json.conditions?.length ?? 0),
    },
    {
      id: "actions_json",
      header: "Действия",
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {row.original.actions_json.map((action, idx) => (
            <Badge key={idx} variant="secondary">
              {ACTION_LABELS[action.type] ?? action.type}
            </Badge>
          ))}
        </div>
      ),
    },
    { accessorKey: "priority", header: "Приоритет" },
    {
      id: "is_enabled",
      header: "Вкл",
      cell: ({ row }) => (
        <Can
          permission={PERMISSIONS.RULES_MANAGE}
          fallback={
            <span className="text-sm text-muted-foreground">
              {row.original.is_enabled ? "Да" : "Нет"}
            </span>
          }
        >
          <Switch
            aria-label={`Правило «${row.original.name}» включено`}
            checked={row.original.is_enabled}
            onCheckedChange={(next) => void toggleRule(row.original, next)}
          />
        </Can>
      ),
    },
    {
      id: "row-actions",
      header: "",
      cell: ({ row }) => (
        <Can permission={PERMISSIONS.RULES_MANAGE}>
          <div className="flex flex-wrap justify-end gap-1">
            <RuleFormDialog
              trigger={
                <Button size="sm" variant="outline">
                  Изменить
                </Button>
              }
              eventTypes={eventTypesRes.data}
              initialData={row.original}
              onSubmitted={reloadRules}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => void runTest(row.original)}
            >
              Тест
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => void removeRule(row.original)}
            >
              Удалить
            </Button>
          </div>
        </Can>
      ),
    },
  ];

  const featureDisabled = [rulesRes.error, eventTypesRes.error].some(
    (err) => err && isFeatureDisabledError(err),
  );
  if (featureDisabled) {
    return (
      <EmptyState
        title="Функция недоступна"
        description="Правила автоматизации не включены для этого тенанта."
      />
    );
  }

  const loading = rulesRes.loading || eventTypesRes.loading;
  const error = rulesRes.error ?? eventTypesRes.error;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Правила автоматизации"
        description="Событийные правила: условия и автоматические действия (задача, уведомление, webhook)."
        actions={
          <Can
            permission={PERMISSIONS.RULES_MANAGE}
            fallback={<Button disabled>Новое правило</Button>}
          >
            <RuleFormDialog
              trigger={<Button>Новое правило</Button>}
              eventTypes={eventTypesRes.data}
              onSubmitted={reloadRules}
            />
          </Can>
        }
      />

      <ErrorState error={error ?? undefined} onRetry={reloadRules} />
      {loading ? <LoadingScreen label="Загрузка правил" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Правил пока нет"
          description="Создайте первое правило автоматизации."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по имени и событию"
          caption="Реестр правил автоматизации"
        />
      ) : null}

      {/* Панели не гейтим на loading: перемонтирование TriggerLogPanel дублировало бы запрос триггеров. */}
      <RuleLibraryPanel
        library={libraryRes.data}
        onInstalled={reloadAfterInstall}
      />
      <DryRunPanel eventTypes={eventTypesRes.data} rules={rulesRes.data} />
      <TriggerLogPanel rules={rulesRes.data} />
    </div>
  );
};

export default RulesPage;
