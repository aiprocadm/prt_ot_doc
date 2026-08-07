"""Unit: BIZ-49 срез-1 — правила ведения клиента аутсорсером (разд. 49.1).

Чистые функции без БД: инварианты режимов ведения, переходы статуса договора,
сигналы портфеля. Режим — не «поле для галочки»: от него зависит, ГДЕ живут
данные клиента, и путаница здесь означает потерю данных при переводе.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.managed_clients.lifecycle import (
    ContractStatus,
    ManagedClientMode,
    ManagedClientTransitionError,
    contract_days_left,
    is_contract_expiring,
    validate_contract_transition,
    validate_conversion_to_dedicated,
    validate_mode_binding,
)

_TODAY = date(2026, 8, 4)


class TestModeBinding:
    def test_lightweight_requires_company(self):
        validate_mode_binding(ManagedClientMode.LIGHTWEIGHT, company_id="c1", tenant_slug=None)
        with pytest.raises(ManagedClientTransitionError):
            validate_mode_binding(ManagedClientMode.LIGHTWEIGHT, company_id=None, tenant_slug=None)

    def test_lightweight_rejects_dedicated_tenant(self):
        """Клиент внутри рабочего пространства не может ещё и владеть своим tenant:
        два места хранения = два расходящихся набора данных."""
        with pytest.raises(ManagedClientTransitionError):
            validate_mode_binding(
                ManagedClientMode.LIGHTWEIGHT, company_id="c1", tenant_slug="client-a"
            )

    def test_dedicated_requires_tenant(self):
        validate_mode_binding(ManagedClientMode.DEDICATED, company_id=None, tenant_slug="client-a")
        with pytest.raises(ManagedClientTransitionError):
            validate_mode_binding(ManagedClientMode.DEDICATED, company_id=None, tenant_slug=None)

    def test_dedicated_keeps_origin_company(self):
        """После перевода Lightweight→Dedicated исходная организация остаётся
        ссылкой на историю в пространстве аутсорсера — это законно."""
        validate_mode_binding(ManagedClientMode.DEDICATED, company_id="c1", tenant_slug="client-a")


class TestContractTransitions:
    @pytest.mark.parametrize(
        "current,target",
        [
            (ContractStatus.DRAFT, ContractStatus.ACTIVE),
            (ContractStatus.DRAFT, ContractStatus.TERMINATED),
            (ContractStatus.ACTIVE, ContractStatus.SUSPENDED),
            (ContractStatus.ACTIVE, ContractStatus.TERMINATED),
            (ContractStatus.SUSPENDED, ContractStatus.ACTIVE),
            (ContractStatus.SUSPENDED, ContractStatus.TERMINATED),
        ],
    )
    def test_allowed(self, current, target):
        validate_contract_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            (ContractStatus.TERMINATED, ContractStatus.ACTIVE),
            (ContractStatus.TERMINATED, ContractStatus.DRAFT),
            (ContractStatus.ACTIVE, ContractStatus.DRAFT),
            (ContractStatus.ACTIVE, ContractStatus.ACTIVE),
        ],
    )
    def test_rejected(self, current, target):
        with pytest.raises(ManagedClientTransitionError):
            validate_contract_transition(current, target)


class TestPortfolioSignals:
    def test_days_left(self):
        assert contract_days_left(date(2026, 8, 14), today=_TODAY) == 10
        assert contract_days_left(date(2026, 8, 4), today=_TODAY) == 0
        assert contract_days_left(date(2026, 8, 1), today=_TODAY) == -3
        assert contract_days_left(None, today=_TODAY) is None

    def test_expiring_only_for_active_contract(self):
        """Истечение — сигнал портфеля, а не свойство даты: у расторгнутого
        договора «истекает через 5 дней» это шум, за которым потеряют настоящие."""
        soon = date(2026, 8, 9)
        assert is_contract_expiring(ContractStatus.ACTIVE, soon, today=_TODAY, horizon_days=30)
        assert not is_contract_expiring(
            ContractStatus.TERMINATED, soon, today=_TODAY, horizon_days=30
        )
        assert not is_contract_expiring(ContractStatus.DRAFT, soon, today=_TODAY, horizon_days=30)

    def test_expired_contract_still_signals(self):
        """Просроченный договор — самый громкий сигнал, а не «уже неважно»."""
        assert is_contract_expiring(
            ContractStatus.ACTIVE, date(2026, 7, 1), today=_TODAY, horizon_days=30
        )

    def test_far_horizon_is_quiet(self):
        assert not is_contract_expiring(
            ContractStatus.ACTIVE, date(2027, 1, 1), today=_TODAY, horizon_days=30
        )

    def test_no_end_date_never_signals(self):
        assert not is_contract_expiring(ContractStatus.ACTIVE, None, today=_TODAY, horizon_days=30)


# --- срез-13: перевод Lightweight → Dedicated (разд. 49.1) -------------------
class TestConversionToDedicated:
    def test_lightweight_with_live_contract_converts(self):
        validate_conversion_to_dedicated(
            mode=ManagedClientMode.LIGHTWEIGHT,
            contract_status=ContractStatus.ACTIVE,
            target_slug="romashka",
        )

    def test_dedicated_cannot_convert_twice(self):
        """Второй перевод означал бы два арендатора с непонятно чьей историей."""
        with pytest.raises(ManagedClientTransitionError):
            validate_conversion_to_dedicated(
                mode=ManagedClientMode.DEDICATED,
                contract_status=ContractStatus.ACTIVE,
                target_slug="romashka",
            )

    def test_terminated_contract_blocks_conversion(self):
        """Перевод — часть живого ведения, а не операция над архивом."""
        with pytest.raises(ManagedClientTransitionError):
            validate_conversion_to_dedicated(
                mode=ManagedClientMode.LIGHTWEIGHT,
                contract_status=ContractStatus.TERMINATED,
                target_slug="romashka",
            )

    def test_draft_and_suspended_contracts_allow_conversion(self):
        for cs in (ContractStatus.DRAFT, ContractStatus.SUSPENDED):
            validate_conversion_to_dedicated(
                mode=ManagedClientMode.LIGHTWEIGHT, contract_status=cs, target_slug="romashka"
            )

    def test_bad_slug_rejected_before_tenant_creation(self):
        """Битое имя схемы БД всплыло бы только при первом обращении к данным."""
        for bad in ("", "R", "ООО-Ромашка", "has space", "-lead", "a" * 64):
            with pytest.raises(ManagedClientTransitionError):
                validate_conversion_to_dedicated(
                    mode=ManagedClientMode.LIGHTWEIGHT,
                    contract_status=ContractStatus.ACTIVE,
                    target_slug=bad,
                )
