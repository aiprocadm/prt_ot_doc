import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { OPEN_STATUS_FILTER } from "@/api/incidents";

/**
 * Плитка «Открытых происшествий» для шапки экрана дисциплины.
 *
 * Доп. №1 разд. 57.4: экран контура — его операционный дашборд, и открытые
 * происшествия своей дисциплины на нём видны. Число считает бэкенд той же
 * формулой, что разрез «по дисциплинам» у директора (поле `incidents_open`
 * сводки); здесь оно только показывается и ведёт в общий реестр с уже
 * выставленным фильтром — своего реестра происшествий контур не заводит.
 * Фильтр — дисциплина И «только открытые» (срез-68): реестр показывает те
 * же записи, что сосчитаны, а не всё той же дисциплины вместе с закрытыми.
 */
export const disciplineIncidentsStat = (
  discipline: string,
  count: number,
): { label: string; value: ReactNode; hint: string } => ({
  label: "Открытых происшествий",
  value: (
    <Link
      to={`/incidents?discipline=${encodeURIComponent(discipline)}&status=${OPEN_STATUS_FILTER}`}
      className="underline"
      title="Открыть реестр происшествий: открытые по дисциплине"
    >
      {count}
    </Link>
  ),
  hint: "по разметке дисциплины; общий реестр",
});
