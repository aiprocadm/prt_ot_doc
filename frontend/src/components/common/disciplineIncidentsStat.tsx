import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/**
 * Плитка «Открытых происшествий» для шапки экрана дисциплины.
 *
 * Доп. №1 разд. 57.4: экран контура — его операционный дашборд, и открытые
 * происшествия своей дисциплины на нём видны. Число считает бэкенд той же
 * формулой, что разрез «по дисциплинам» у директора (поле `incidents_open`
 * сводки); здесь оно только показывается и ведёт в общий реестр с уже
 * выставленным фильтром — своего реестра происшествий контур не заводит.
 */
export const disciplineIncidentsStat = (
  discipline: string,
  count: number,
): { label: string; value: ReactNode; hint: string } => ({
  label: "Открытых происшествий",
  value: (
    <Link
      to={`/incidents?discipline=${encodeURIComponent(discipline)}`}
      className="underline"
      title="Открыть реестр происшествий с фильтром по дисциплине"
    >
      {count}
    </Link>
  ),
  hint: "по разметке дисциплины; общий реестр",
});
