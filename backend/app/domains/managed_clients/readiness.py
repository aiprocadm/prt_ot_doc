"""BIZ-51 срез-5 (Доп. №1 разд. 51.3): эталон соответствия и светофор клиента.

ТЗ: «для каждого долгосрочного клиента — „эталон соответствия“: что у него
должно быть; система непрерывно сравнивает факт с эталоном и показывает
разрыв». Ключевое отличие от «Центра внимания» (BIZ-49): тот показывает
ПРОСРОЧКИ существующих записей, а эталон — ОТСУТСТВИЕ положенного. Сотрудник,
которому по норме должности положен медосмотр, а записи нет вовсе, в «Центре
внимания» не появится никогда: там нечему просрочиваться.

**Здесь остались только местные имена.** Сами правила переехали в ядро
(``app/core/discipline_status.py``, BIZ-54-57 срез-3): тот же светофор рисует
карточка площадки 360°, и второй экземпляр правил разошёлся бы с первым на
первой же правке — ровно та причина, по которой в срезе-1 в ядро переехал
словарь дисциплин. Здесь — псевдонимы, чтобы не переписывать домен и его
тесты.
"""

from __future__ import annotations

from app.core.discipline_status import (
    DisciplineCounts,
    DisciplineStatus,
    TrafficLight,
    build_discipline_statuses,
    evaluate_counts,
    training_status,
    worst_light,
)
from app.core.disciplines import (
    DISCIPLINE_TITLES,
    MEASURED_DISCIPLINES,
    UNMEASURED_DISCIPLINES,
    Discipline,
)

__all__ = [
    "Direction",
    "DirectionCounts",
    "DirectionReadiness",
    "TrafficLight",
    "MEASURED_DIRECTIONS",
    "UNMEASURED_DIRECTIONS",
    "build_directions",
    "evaluate_direction",
    "training_readiness",
    "worst_light",
]

#: Направления светофора — это дисциплины ТЗ (Доп. №1 разд. 54–57), и живут
#: они в ядре: тот же словарь красит Центр внимания (BIZ-54-57 срез-1). Здесь
#: только псевдонимы под местные имена — второй словарь с теми же словами
#: разошёлся бы с первым на первой правке.
Direction = Discipline
DIRECTION_TITLES = DISCIPLINE_TITLES
MEASURED_DIRECTIONS = MEASURED_DISCIPLINES
UNMEASURED_DIRECTIONS = UNMEASURED_DISCIPLINES

DirectionCounts = DisciplineCounts
DirectionReadiness = DisciplineStatus
evaluate_direction = evaluate_counts
training_readiness = training_status
build_directions = build_discipline_statuses
