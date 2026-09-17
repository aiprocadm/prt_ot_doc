"""BIZ-52 срез-7: разбор эталонного набора (разд. 52.3, первый пункт).

Правила чистые — проверяются словарями без базы.
"""

from __future__ import annotations

import json
import pathlib

from app.domains.reseller.starter_pack import (
    APPLICABLE_KINDS,
    NON_TABLE_KINDS,
    plan_starter_pack,
)

PACK_ROOT = pathlib.Path(__file__).resolve().parents[1] / "seed" / "tenant_starter_packs" / "v1"


class TestРазборНабора:
    def test_применимые_виды_попадают_в_план(self) -> None:
        plan = plan_starter_pack({"reference_data": {"positions": ["Директор", "Эколог"]}})
        assert plan.apply == {"positions": ["Директор", "Эколог"]}

    def test_перечисления_помечаются_причиной_а_не_молчанием(self) -> None:
        """«Пропущено» без объяснения читается как недоработка."""

        plan = plan_starter_pack({"reference_data": {"incident_types": ["Микротравма"]}})

        assert plan.apply == {}
        assert "incident_types" in plan.skipped
        assert plan.skipped["incident_types"]

    def test_незнакомый_ключ_замечается(self) -> None:
        """Файл эталона мог уйти вперёд кода — это надо увидеть, а не проглотить."""

        plan = plan_starter_pack({"reference_data": {"чтото_новое": ["А"]}})

        assert plan.unknown == ["чтото_новое"]

    def test_пустой_набор_не_ломается(self) -> None:
        assert plan_starter_pack({}).apply == {}
        assert plan_starter_pack({"reference_data": None}).apply == {}

    def test_пустые_названия_отбрасываются(self) -> None:
        plan = plan_starter_pack(
            {"reference_data": {"hazards": ["Пожар", "   ", "", "Электротравма"]}}
        )
        assert plan.apply["hazards"] == ["Пожар", "Электротравма"]

    def test_дубли_убираются_без_учёта_регистра_и_пробелов(self) -> None:
        """Две строки «Пожар» сделали бы справочник грязным с первого дня."""

        plan = plan_starter_pack({"reference_data": {"hazards": ["Пожар", "пожар ", " ПОЖАР"]}})
        assert plan.apply["hazards"] == ["Пожар"]

    def test_порядок_файла_сохраняется(self) -> None:
        """Порядок задан человеком: «Директор» перед «Мастером участка» не случайность."""

        names = ["Директор", "Специалист ОТ", "Мастер участка"]
        plan = plan_starter_pack({"reference_data": {"positions": names}})
        assert plan.apply["positions"] == names

    def test_нестроковые_элементы_игнорируются(self) -> None:
        plan = plan_starter_pack({"reference_data": {"hazards": ["Пожар", 42, None, {"x": 1}]}})
        assert plan.apply["hazards"] == ["Пожар"]

    def test_вид_без_названий_в_план_не_попадает(self) -> None:
        """Пустой список — не повод объявлять, что мы что-то создали."""

        plan = plan_starter_pack({"reference_data": {"positions": []}})
        assert "positions" not in plan.apply


class TestНастоящиеФайлыЭталонов:
    """Разбор проверяется на ФАЙЛАХ из репозитория, а не только на выдумках.

    Иначе правила разошлись бы с данными, и «эталон применён» снова означало бы
    не то, что написано.
    """

    def test_default_даёт_непустой_план(self) -> None:
        payload = json.loads((PACK_ROOT / "default.json").read_text(encoding="utf-8"))
        plan = plan_starter_pack(payload)

        assert plan.apply["positions"]
        assert plan.apply["hazards"]
        assert plan.apply["controls"]

    def test_в_default_нет_незнакомых_ключей(self) -> None:
        payload = json.loads((PACK_ROOT / "default.json").read_text(encoding="utf-8"))
        plan = plan_starter_pack(payload)

        assert plan.unknown == [], (
            "файл эталона содержит ключ, который код не знает — "
            "либо добавить его в APPLICABLE_KINDS, либо объяснить в NON_TABLE_KINDS"
        )

    def test_каждый_ключ_default_объяснён(self) -> None:
        payload = json.loads((PACK_ROOT / "default.json").read_text(encoding="utf-8"))
        keys = set(payload["reference_data"])

        assert keys <= set(APPLICABLE_KINDS) | set(NON_TABLE_KINDS)
