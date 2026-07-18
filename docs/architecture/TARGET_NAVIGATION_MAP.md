# Target Navigation Map

## Доменная структура

- Компании
- Сотрудники
- Документы
- Обучение
- Риски
- Проверки
- Задачи
- Отчеты
- Администрирование

## Принцип вложенности

`Объект -> Действия -> История -> Связанные сущности`

### Пример: Company

- Карточка компании
- Действия: создать документ, задачу, риск, проверку
- История: документы, активности, события
- Связанные сущности: сотрудники, риски, проверки

## Логика группировки

1. Пользователь входит в домен через сущность, а не через технический процесс.
2. Глобальные разделы остаются для мониторинга, но action-first сценарии доступны в контексте сущности.
3. Термины меню отражают бизнес-значение, а не внутреннюю реализацию.
4. Разделы с одинаковой природой действий объединяются (например, проверки и предписания).

## Навигационный каркас

```mermaid
flowchart TD
  app[AppNavigation]
  app --> companies[Companies]
  app --> employees[Employees]
  app --> documents[Documents]
  app --> training[Training]
  app --> risks[Risks]
  app --> inspections[Inspections]
  app --> tasks[Tasks]
  app --> reports[Reports]
  app --> admin[Administration]

  companies --> companyCard[CompanyCard]
  companyCard --> companyActions[Actions]
  companyCard --> companyHistory[History]
  companyCard --> companyRelated[RelatedEntities]
```

