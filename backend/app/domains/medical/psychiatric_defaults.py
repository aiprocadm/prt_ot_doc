"""Standard ПП РФ № 695 виды деятельности requiring обязательное психиатрическое
освидетельствование (приказ Минздрава № 342н). Single source for the demo seed and the
POST /medical/psychiatric/activity-types/seed-defaults endpoint.

Formulations are conservative paraphrases of the ПП-695 приложение — verify exact wording
against the primary source before any print/legal use. Periodicity 1825 days = 5 лет.
"""

from __future__ import annotations

# (code, name, interval_days)
PSYCHIATRIC_ACTIVITY_DEFAULTS: tuple[tuple[str, str, int], ...] = (
    ("transport", "Управление транспортными средствами", 1825),
    ("height", "Работы на высоте", 1825),
    ("electrical", "Обслуживание и ремонт действующих электроустановок", 1825),
    ("forestry", "Работы в лесной охране, валка и транспортировка леса", 1825),
    ("weapons", "Работы, связанные с оборотом и ношением оружия", 1825),
    ("pressure_vessels", "Обслуживание сосудов, работающих под давлением", 1825),
    ("rescue_fire", "Аварийно-спасательные работы и тушение пожаров", 1825),
    ("underground", "Подземные работы", 1825),
    ("railway", "Работы, связанные с движением поездов и маневровой работой", 1825),
)
