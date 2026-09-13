/**
 * Срез-178: подписи уведомлений по-русски.
 *
 * Экран уведомлений показывал четыре поля так, как они записаны в коде:
 * вид письма (`TrainingDueSoon`), канал (`inapp`), важность (`medium`) и
 * состояние (`queued`). Человек видел латиницу и должен был догадываться сам,
 * а фильтр по виду предлагал те же коды.
 *
 * Составы сверяются с перечислениями сервера сторожем
 * `tests/test_notifications_vocab.py`: пропущенный вид снова показался бы
 * кодом, лишний — означал бы, что словарь оброс мёртвыми строками.
 */

export const NOTIFICATION_TYPE_LABELS: Record<string, string> = {
  JobStatusChanged: "Изменилось состояние задания",
  DocumentGenerated: "Документ сформирован",
  DocumentExported: "Документы выгружены",
  DocumentSigned: "Документ подписан",
  TrainingDueSoon: "Скоро обучение",
  TrainingOverdue: "Обучение просрочено",
  TrainingCompleted: "Обучение завершено",
  PPEExpirySoon: "Истекает срок носки СИЗ",
  PPEIssueCreated: "Выданы СИЗ",
  MedicalDueSoon: "Скоро медосмотр",
  PermitExpirySoon: "Истекает допуск",
  InspectionPlanned: "Запланирована проверка",
  InspectionOverdue: "Проверка просрочена",
  IncidentAssigned: "Назначено происшествие",
  CADueSoon: "Скоро срок мероприятия",
  ApprovalDeadline: "Срок согласования",
  MedicalOverdue: "Медосмотр просрочен",
  PPEOverdue: "СИЗ просрочены",
  IncidentCreated: "Зарегистрировано происшествие",
  InspectionCreated: "Заведена проверка",
  PrescriptionOverdue: "Предписание просрочено",
  PackageRunCompleted: "Комплект собран",
  PackageRunFailed: "Сборка комплекта не удалась",
  IntegrationError: "Ошибка интеграции",
  EdoStatusChanged: "Изменился статус в ЭДО",
  BillingLimitWarning: "Приближается лимит тарифа",
  AutomationRule: "Сработало правило автоматизации",
  DisciplineReport: "Отчёт по дисциплинам",
};

export const NOTIFICATION_CHANNEL_LABELS: Record<string, string> = {
  email: "Почта",
  telegram: "Телеграм",
  inapp: "В системе",
  webhook: "Вебхук",
};

export const NOTIFICATION_STATUS_LABELS: Record<string, string> = {
  queued: "В очереди",
  sent: "Отправлено",
  failed: "Сбой",
  canceled: "Отменено",
  read: "Прочитано",
};

export const NOTIFICATION_PRIORITY_LABELS: Record<string, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая",
};

/** Подпись, а если вид неизвестен — сам код (молчать нельзя). */
export const notificationTypeLabel = (code: string): string =>
  NOTIFICATION_TYPE_LABELS[code] ?? code;

export const notificationChannelLabel = (code: string): string =>
  NOTIFICATION_CHANNEL_LABELS[code] ?? code;

export const notificationStatusLabel = (code: string): string =>
  NOTIFICATION_STATUS_LABELS[code] ?? code;

export const notificationPriorityLabel = (code: string): string =>
  NOTIFICATION_PRIORITY_LABELS[code] ?? code;
