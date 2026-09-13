export const wizardSteps = [
  { id: 1, title: "Пресет", description: "Выбор проекта или ручной режим" },
  { id: 2, title: "Файл", description: "Загрузка CSV/XLSX" },
  { id: 3, title: "Маппинг", description: "Колонки → поля" },
  { id: 4, title: "Шаблон", description: "Template code + version" },
  { id: 5, title: "Колонтитулы", description: "Параметры макета" },
  // Срез-154: шаг больше не делает пробную замену — старый контракт снят
  // с сервера. Название и описание не должны обещать того, чего нет.
  { id: 6, title: "Замена", description: "Пока недоступна" },
  { id: 7, title: "Запуск", description: "Batch/queue/idempotency" },
  { id: 8, title: "Контроль", description: "Предпросмотр и ошибки" },
  { id: 9, title: "Экспорт", description: "ZIP/PDF" },
  { id: 10, title: "Архив", description: "Архив + ЭДО (MVP)" },
] as const;

export const previewSectionCards = [
  { key: "header_first", label: "Header first" },
  { key: "header_odd", label: "Header odd" },
  { key: "header_even", label: "Header even" },
  { key: "footer_first", label: "Footer first" },
  { key: "footer_odd", label: "Footer odd" },
  { key: "footer_even", label: "Footer even" },
] as const;
