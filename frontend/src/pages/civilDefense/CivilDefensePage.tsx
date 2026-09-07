import { type ColumnDef } from "@tanstack/react-table";
import { useCallback, useMemo, useState } from "react";

import {
  civilDefenseApi,
  type CdDocumentDto,
  type DrillDto,
  type FormationDto,
  type ProfileDto,
  type TrainingProgramDto,
} from "@/api/civilDefense";
import { fetchAllPersons } from "@/api/personsApi";
import { sitesApi } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { disciplineIncidentsStat } from "@/components/common/disciplineIncidentsStat";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { CdDocumentFormDialog } from "@/features/civil-defense/CdDocumentFormDialog";
import { CdDrillFormDialog } from "@/features/civil-defense/CdDrillFormDialog";
import { CdFormationFormDialog } from "@/features/civil-defense/CdFormationFormDialog";
import { CdFormationMembersDialog } from "@/features/civil-defense/CdFormationMembersDialog";
import { CdProfileFormDialog } from "@/features/civil-defense/CdProfileFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * ГО и ЧС: реестр нештатных формирований (Доп. №1 разд. 56.1, срез-1).
 *
 * До этого экрана по разд. 56 не было НИЧЕГО: ни сущностей, ни ручек, ни
 * страницы — дисциплина существовала словарной строкой, а весь контент
 * сводился к комплекту документов GOCHS_BASE.
 */
const FORMATION_COLUMNS: ColumnDef<FormationDto, unknown>[] = [
  { accessorKey: "name", header: "Наименование" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "purpose",
    header: "Назначение",
    cell: ({ row }) => row.original.purpose || "—",
  },
  {
    accessorKey: "commander_name",
    header: "Командир",
    cell: ({ row }) => row.original.commander_name || "не назначен",
  },
  {
    accessorKey: "members_active",
    header: "В составе",
    cell: ({ row }) =>
      row.original.members_active > 0
        ? `${row.original.members_active}`
        : "состав не внесён",
  },
];

const DRILL_COLUMNS: ColumnDef<DrillDto, unknown>[] = [
  { accessorKey: "title", header: "Учение" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "planned_on",
    header: "По плану",
    cell: ({ row }) => formatDate(row.original.planned_on),
  },
  {
    // Срез-109: дата проведения и состояние — одна колонка: колонка действий
    // стала бы восьмой и вывела бы таблицу за UX-бюджет.
    accessorKey: "status_label",
    header: "Состояние",
    cell: ({ row }) => (
      <span>
        {row.original.status_label}
        {row.original.held_on ? (
          <span className="ml-1 text-muted-foreground">
            {formatDate(row.original.held_on)}
          </span>
        ) : null}
      </span>
    ),
  },
  {
    accessorKey: "formation_name",
    header: "Формирование",
    cell: ({ row }) => row.original.formation_name || "весь персонал",
  },
  {
    accessorKey: "outcome_label",
    header: "Результат",
    cell: ({ row }) => row.original.outcome_label || "—",
  },
];

const PROFILE_COLUMNS: ColumnDef<ProfileDto, unknown>[] = [
  {
    accessorKey: "site_name",
    header: "Объект",
    cell: ({ row }) => row.original.site_name || "объект не найден",
  },
  {
    accessorKey: "category_label",
    header: "Категория по ГО",
    cell: ({ row }) => row.original.category_label,
  },
  {
    accessorKey: "decision_number",
    header: "Решение о категорировании",
    cell: ({ row }) => row.original.decision_number || "реквизиты не внесены",
  },
  {
    accessorKey: "responsible",
    header: "Ответственный",
    cell: ({ row }) => row.original.responsible || "не назначен",
  },
];

const CD_DOCUMENT_COLUMNS: ColumnDef<CdDocumentDto, unknown>[] = [
  { accessorKey: "title", header: "Документ" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "approved_on",
    header: "Утверждён",
    cell: ({ row }) =>
      row.original.approved_on ? formatDate(row.original.approved_on) : "—",
  },
  {
    accessorKey: "review_due",
    header: "Пересмотр до",
    cell: ({ row }) =>
      row.original.review_due
        ? formatDate(row.original.review_due)
        : "бессрочно",
  },
  {
    accessorKey: "review_status_label",
    header: "Состояние",
    cell: ({ row }) => row.original.review_status_label,
  },
];

const TRAINING_PROGRAM_COLUMNS: ColumnDef<TrainingProgramDto, unknown>[] = [
  { accessorKey: "title", header: "Программа" },
  {
    accessorKey: "code",
    header: "Код",
    cell: ({ row }) => row.original.code || "—",
  },
  {
    accessorKey: "duration_hours",
    header: "Часов",
    cell: ({ row }) =>
      row.original.duration_hours != null
        ? `${row.original.duration_hours}`
        : "не указано",
  },
  {
    accessorKey: "valid_period_days",
    header: "Срок действия",
    cell: ({ row }) =>
      row.original.valid_period_days != null
        ? `${row.original.valid_period_days} дн.`
        : "бессрочно",
  },
];

const CivilDefensePage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ, ПромБеза и экологии): реестр
  // формирований и план-график учений — разные задачи специалиста.
  const [section, setSection] = useState<
    "formations" | "drills" | "planning" | "training"
  >("formations");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        formations: await civilDefenseApi.listFormations(),
        // Люди — ядровой справочник: командира формирования выбирают, а не
        // вводят id (срез-109).
        persons: await fetchAllPersons(),
        // Площадки — ядровой справочник: сведения по ГО и документы
        // привязывают к площадке выбором (срез-110).
        sites: (await sitesApi.list()).items,
        drills: await civilDefenseApi.listDrills(),
        profiles: await civilDefenseApi.listProfiles(),
        documents: await civilDefenseApi.listDocuments(),
        programs: await civilDefenseApi.listTrainingPrograms(),
        readiness: await civilDefenseApi.readiness(),
      }),
      [],
    ),
    initialData: {
      formations: [] as FormationDto[],
      persons: [] as Awaited<ReturnType<typeof fetchAllPersons>>,
      sites: [] as Awaited<ReturnType<typeof sitesApi.list>>["items"],
      drills: [] as DrillDto[],
      profiles: [] as ProfileDto[],
      documents: [] as CdDocumentDto[],
      programs: [] as TrainingProgramDto[],
      readiness: {
        incidents_open: 0,
        total_formations: 0,
        by_kind: { nasf: 0, nfgo: 0 },
        without_commander: 0,
        members_active: 0,
        drills_total: 0,
        drills_overdue: 0,
        drills_held_this_year: 0,
        profiles_total: 0,
        profiles_by_category: {},
        planning_documents: 0,
        planning_review_overdue: 0,
        training_programs: 0,
      },
    },
    errorMessage: "Не удалось загрузить формирования ГО и ЧС",
  });

  const registry = useLocalRegistry({
    items: data.formations,
    match: (item, query) =>
      [item.name, item.kind_label, item.purpose, item.commander_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const drillRegistry = useLocalRegistry({
    items: data.drills,
    match: (item, query) =>
      [item.title, item.kind_label, item.status_label, item.formation_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const profileRegistry = useLocalRegistry({
    items: data.profiles,
    match: (item, query) =>
      [
        item.site_name,
        item.category_label,
        item.decision_number,
        item.responsible,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const documentRegistry = useLocalRegistry({
    items: data.documents,
    match: (item, query) =>
      [item.title, item.kind_label, item.number, item.review_status_label]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const programRegistry = useLocalRegistry({
    items: data.programs,
    match: (item, query) =>
      [item.title, item.code]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = data;

  // Срез-109: колонка действий добавляется здесь — формам нужны справочники и
  // перезагрузка, которых у констант колонок нет (приём среза-107).
  const formationColumns = useMemo(
    () => [
      ...FORMATION_COLUMNS,
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }: { row: { original: FormationDto } }) => (
          <div className="flex gap-1">
            <CdFormationFormDialog
              persons={data.persons}
              initialData={row.original}
              onSubmitted={() => void reload()}
              trigger={
                <Button variant="ghost" size="sm">
                  Изменить
                </Button>
              }
            />
            {/* Срез-110: состав читается по кнопке — списков столько же,
                сколько формирований, и грузить их все ради реестра незачем. */}
            <CdFormationMembersDialog
              formation={row.original}
              persons={data.persons}
              onChanged={() => void reload()}
              trigger={
                <Button variant="ghost" size="sm">
                  Состав
                </Button>
              }
            />
          </div>
        ),
      },
    ],
    [data.persons, reload],
  );

  const profileColumns = useMemo(
    () => [
      ...PROFILE_COLUMNS,
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }: { row: { original: ProfileDto } }) => (
          <CdProfileFormDialog
            sites={data.sites}
            initialData={row.original}
            onSubmitted={() => void reload()}
            trigger={
              <Button variant="ghost" size="sm">
                Изменить
              </Button>
            }
          />
        ),
      },
    ],
    [data.sites, reload],
  );

  const documentColumns = useMemo(
    () => [
      ...CD_DOCUMENT_COLUMNS,
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }: { row: { original: CdDocumentDto } }) => (
          <CdDocumentFormDialog
            sites={data.sites}
            initialData={row.original}
            onSubmitted={() => void reload()}
            trigger={
              <Button variant="ghost" size="sm">
                Изменить
              </Button>
            }
          />
        ),
      },
    ],
    [data.sites, reload],
  );

  const drillColumns = useMemo(
    () => [
      ...DRILL_COLUMNS,
      {
        id: "actions",
        header: "Действия",
        // Пока учение не проведено, кнопка зовёт внести протокол (приём
        // среза-104): подпись говорит, что делать дальше.
        cell: ({ row }: { row: { original: DrillDto } }) => (
          <CdDrillFormDialog
            formations={data.formations}
            initialData={row.original}
            onSubmitted={() => void reload()}
            trigger={
              <Button variant="ghost" size="sm">
                {row.original.held_on ? "Изменить" : "Протокол"}
              </Button>
            }
          />
        ),
      },
    ],
    [data.formations, reload],
  );

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="ГО и ЧС"
        description="Нештатные формирования гражданской обороны: НАСФ и НФГО, командиры и составы из сотрудников организации."
        stats={[
          { label: "Формирований", value: readiness.total_formations },
          { label: "НАСФ", value: readiness.by_kind.nasf ?? 0 },
          { label: "НФГО", value: readiness.by_kind.nfgo ?? 0 },
          // ФАКТ о внесённом, а не вердикт: штат формирования платформа
          // не знает.
          { label: "Без командира", value: readiness.without_commander },
          { label: "Людей в составах", value: readiness.members_active },
          // Разд. 56.1 «учения»: просрочка — факт по внесённому плану, а не
          // вывод платформы о нарушении периодичности.
          { label: "Учения просрочены", value: readiness.drills_overdue },
          {
            label: "Проведено за год",
            value: readiness.drills_held_this_year,
          },
          // Разд. 56.1 «категорирование и планирование». Просрочка — по
          // ВНЕСЁННОМУ сроку пересмотра, а не по норме, которой платформа
          // не знает.
          {
            label: "Пересмотр просрочен",
            value: readiness.planning_review_overdue,
          },
          // Разд. 56.1 «программы обучения»: программы ядра с дисциплиной ГО.
          // Реестром владеет раздел обучения — здесь только счётчик.
          { label: "Программ обучения", value: readiness.training_programs },
          // Доп. №1 разд. 57.4: происшествия контура — той же формулой, что
          // разрез у директора; ссылка ведёт в общий реестр (срез-49).
          disciplineIncidentsStat("civil_defense", readiness.incidents_open),
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["formations", "Формирования"],
            ["drills", "Учения и тренировки"],
            ["planning", "Категорирование и планы"],
            ["training", "Программы обучения"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            size="sm"
            variant={section === key ? "secondary" : "outline"}
            onClick={() => setSection(key)}
          >
            {label}
          </Button>
        ))}
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка формирований" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент категории НВОС и интервала
        тренировок ПБ): обязанность создавать формирования и их штат следуют
        из категории организации по ГО и решений органа управления ГОЧС —
        платформа хранит внесённое, а не решает за орган.
      */}
      {section === "formations" && !loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Нужно ли организации формирование и каков его штат, определяют
          категория по гражданской обороне и орган управления ГОЧС: платформа
          ведёт реестр внесённого и не выносит вердиктов.
        </p>
      ) : null}
      {/*
        Срез-109: ручки формирований (срез-1 контура) работали только через
        API — реестр звал «внесите нештатные формирования», а внести их было
        негде.
      */}
      {section === "formations" && !loading && !error ? (
        <div>
          <CdFormationFormDialog
            persons={data.persons}
            onSubmitted={() => void reload()}
            trigger={<Button>Завести формирование</Button>}
          />
        </div>
      ) : null}
      {section === "formations" &&
      !loading &&
      !error &&
      registry.total === 0 ? (
        <EmptyState
          title="Формирования не заведены"
          description="Внесите нештатные формирования: НАСФ (аварийно-спасательные) и НФГО (по обеспечению мероприятий ГО), их назначение и командиров из числа сотрудников."
        />
      ) : null}
      {section === "formations" && !loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={formationColumns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по названию, виду, командиру"
          caption="Реестр нештатных формирований"
        />
      ) : null}
      {section === "drills" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: периодичность учений установлена
            постановлением Правительства и зависит от категории организации по
            ГО — платформа ведёт внесённый план-график и не назначает сроки.
          */}
          <p className="text-sm text-muted-foreground">
            Периодичность учений установлена постановлением и категорией
            организации по гражданской обороне: платформа ведёт внесённый
            план-график и журнал проведённых, но сроки не назначает.
            «Просрочено» — это план, срок которого прошёл, а протокола нет.
          </p>
          {/* Срез-109: учение планируется здесь же, протокол — правкой. */}
          <div>
            <CdDrillFormDialog
              formations={data.formations}
              onSubmitted={() => void reload()}
              trigger={<Button>Запланировать учение</Button>}
            />
          </div>
          {drillRegistry.total === 0 ? (
            <EmptyState
              title="План-график учений не заведён"
              description="Внесите учения и тренировки: командно-штабные, тактико-специальные, комплексные и объектовые. У проведённого обязателен результат — без него анализировать нечего."
            />
          ) : (
            <RegistryTable
              columns={drillColumns}
              data={drillRegistry.pagedItems}
              pageIndex={drillRegistry.pageIndex}
              pageSize={drillRegistry.pageSize}
              total={drillRegistry.total}
              onPageChange={drillRegistry.onPageChange}
              onPageSizeChange={drillRegistry.onPageSizeChange}
              onSearchChange={drillRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, виду, состоянию"
              caption="План-график учений и журнал проведённых"
            />
          )}
        </>
      ) : null}
      {section === "planning" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: категорирование выполняет орган по
            показателям (численность работающих, оборонное значение, опасные
            производства), которых в системе нет. Платформа хранит внесённое.
          */}
          <p className="text-sm text-muted-foreground">
            Категорию объекта по ГО присваивает орган по своим показателям:
            платформа хранит внесённое решение и не предлагает категорию сама.
            «Категория не присвоена» — это внесённое сведение, а не пустая
            клетка. Пустой срок пересмотра документа означает «бессрочно».
          </p>
          {/*
            Срез-110: сведения по ГО и документы планирования (срез-3 контура)
            заводились только через API. Сведения привязаны к площадке,
            поэтому кнопка есть, когда площадки заведены.
          */}
          <div className="flex flex-wrap gap-2">
            {data.sites.length > 0 ? (
              <CdProfileFormDialog
                sites={data.sites}
                onSubmitted={() => void reload()}
                trigger={<Button>Внести сведения по ГО</Button>}
              />
            ) : null}
            <CdDocumentFormDialog
              sites={data.sites}
              onSubmitted={() => void reload()}
              trigger={<Button>Завести документ</Button>}
            />
          </div>
          {profileRegistry.total === 0 ? (
            <EmptyState
              title="Сведения по ГО не внесены"
              description="Внесите категорию объектов по гражданской обороне и реквизиты решения о категорировании: от категории зависят состав сил, планы и отчётность."
            />
          ) : (
            <RegistryTable
              columns={profileColumns}
              data={profileRegistry.pagedItems}
              pageIndex={profileRegistry.pageIndex}
              pageSize={profileRegistry.pageSize}
              total={profileRegistry.total}
              onPageChange={profileRegistry.onPageChange}
              onPageSizeChange={profileRegistry.onPageSizeChange}
              onSearchChange={profileRegistry.onSearchChange}
              searchPlaceholder="Поиск по объекту, категории, решению"
              caption="Сведения по гражданской обороне"
            />
          )}
          {documentRegistry.total > 0 ? (
            <RegistryTable
              columns={documentColumns}
              data={documentRegistry.pagedItems}
              pageIndex={documentRegistry.pageIndex}
              pageSize={documentRegistry.pageSize}
              total={documentRegistry.total}
              onPageChange={documentRegistry.onPageChange}
              onPageSizeChange={documentRegistry.onPageSizeChange}
              onSearchChange={documentRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, виду, номеру"
              caption="Планы, паспорт безопасности, приказы и положения"
            />
          ) : null}
        </>
      ) : null}
      {section === "training" && !loading && !error ? (
        <>
          {/*
            Реестром программ контур ГО НЕ владеет: заводятся и правятся они в
            разделе обучения (принцип «ядро не дублируется»). Здесь показана
            только своя часть — программы, размеченные дисциплиной ГО и ЧС.
          */}
          <p className="text-sm text-muted-foreground">
            Здесь показаны программы обучения, отнесённые к дисциплине «ГО и
            ЧС». Заводятся и правятся они в разделе «Обучение»: реестр программ
            один на весь продукт, и второй вход в него означал бы два места
            правды. Какие программы нужны организации, определяют категория по
            ГО и решения органа — платформа этого не решает.
          </p>
          {programRegistry.total === 0 ? (
            <EmptyState
              title="Программы обучения по ГО не размечены"
              description="Отнесите программы к дисциплине «ГО и ЧС» в разделе «Обучение» — например курсовое обучение работающего населения. Без отнесения программа неотличима от курса по охране труда."
            />
          ) : (
            <RegistryTable
              columns={TRAINING_PROGRAM_COLUMNS}
              data={programRegistry.pagedItems}
              pageIndex={programRegistry.pageIndex}
              pageSize={programRegistry.pageSize}
              total={programRegistry.total}
              onPageChange={programRegistry.onPageChange}
              onPageSizeChange={programRegistry.onPageSizeChange}
              onSearchChange={programRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию и коду"
              caption="Программы обучения по ГО и ЧС"
            />
          )}
        </>
      ) : null}
    </div>
  );
};

export default CivilDefensePage;
