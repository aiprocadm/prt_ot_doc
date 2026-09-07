import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Опасный производственный объект (разд. 54.2, срез-105).
 *
 * ГРАНИЦА: класс опасности присваивается при регистрации в госреестре по
 * признакам объекта — платформа его не вычисляет и не подсказывает. Номер в
 * реестре обязателен: ОПО без номера не существует. Исключение из реестра —
 * состояние, а не удаление: история эксплуатации остаётся.
 */
export const opoFacilityFormSchema = z
  .object({
    name: z.string().trim().min(1, "Назовите объект"),
    register_number: z
      .string()
      .trim()
      .min(1, "Внесите номер из свидетельства о регистрации"),
    hazard_class: z.string().trim().min(1, "Выберите класс опасности"),
    site_id: optionalText,
    status: z.string().trim().min(1, "Выберите состояние"),
    registered_on: optionalText,
    excluded_on: optionalText,
    responsible: optionalText,
    notes: optionalText,
  })
  // Исключённый из реестра без даты — запись, по которой нельзя ответить
  // надзору «когда»: состояние говорит «исключён», а документа за ним нет.
  .refine((v) => v.status !== "excluded" || Boolean(v.excluded_on), {
    message: "У исключённого из реестра нужна дата исключения",
    path: ["excluded_on"],
  });

export type OpoFacilityFormValues = z.infer<typeof opoFacilityFormSchema>;

/**
 * Техническое устройство на ОПО (разд. 54.2, срез-105).
 *
 * ГРАНИЦА: платформа НЕ решает, нужна ли устройству экспертиза — это зависит
 * от типа, документации и норм ФНП. Поля заключения ЭПБ необязательны, а
 * «заключения нет» — отдельное состояние, а не разновидность просрочки.
 */
export const opoDeviceFormSchema = z.object({
  facility_id: z.string().trim().min(1, "Выберите объект (ОПО)"),
  kind: z.string().trim().min(1, "Выберите вид устройства"),
  name: z.string().trim().min(1, "Назовите устройство"),
  serial_number: optionalText,
  status: z.string().trim().min(1, "Выберите состояние"),
  lifetime_until: optionalText,
  commissioned_on: optionalText,
  epb_conclusion_number: optionalText,
  epb_registered_on: optionalText,
  epb_valid_until: optionalText,
  notes: optionalText,
});

export type OpoDeviceFormValues = z.infer<typeof opoDeviceFormSchema>;

/**
 * Работа по устройству (разд. 54.2, срез-105).
 *
 * У экспертизы обязателен номер заключения: именно он вносится в реестр
 * Ростехнадзора и предъявляется проверяющему (правило сервера — здесь оно
 * показывается до запроса). Срок эксплуатации продлевает ТОЛЬКО положительная
 * экспертиза: иначе «протёрли и записали ТО» продлевало бы жизнь устройству
 * на бумаге.
 */
export const opoDeviceWorkFormSchema = z
  .object({
    device_id: z.string().trim().min(1, "Выберите устройство"),
    kind: z.string().trim().min(1, "Выберите вид работы"),
    performed_on: z.string().trim().min(1, "Внесите дату работы"),
    result: z.string().trim().min(1, "Выберите результат"),
    conclusion_number: optionalText,
    performer: optionalText,
    next_due: optionalText,
    notes: optionalText,
  })
  .refine((v) => v.kind !== "epb" || Boolean(v.conclusion_number), {
    message:
      "Для экспертизы обязателен номер заключения: он вносится в реестр Ростехнадзора",
    path: ["conclusion_number"],
  });

export type OpoDeviceWorkFormValues = z.infer<typeof opoDeviceWorkFormSchema>;
