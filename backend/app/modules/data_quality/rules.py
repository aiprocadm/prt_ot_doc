"""Data quality rules and rule engine."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import DataQualityIssue, IssueSeverity, IssueType

logger = logging.getLogger("app.modules.data_quality")


class DataQualityRule(ABC):
    """Base class for data quality rules."""

    def __init__(self, tenant_id: str, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self.issues: list[DataQualityIssue] = []
        self.total_checked = 0

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Rule name."""
        pass

    @property
    @abstractmethod
    def rule_description(self) -> str:
        """Human-readable rule description."""
        pass

    @abstractmethod
    async def check(self) -> None:
        """Run the rule check. Must populate self.issues and self.total_checked."""
        pass


class MissingMandatoryFieldsRule(DataQualityRule):
    """Check for missing mandatory fields in critical entities."""

    @property
    def rule_name(self) -> str:
        return "missing_mandatory_fields"

    @property
    def rule_description(self) -> str:
        return "Check for missing mandatory fields in employees, sites, and contractors"

    async def check(self) -> None:
        """Check for entities with missing critical fields."""
        try:
            # This is a placeholder implementation
            # In production, would query actual models when they become available
            # For now, just mark as checked with 0 issues
            self.total_checked = 0
            self.issues = []
        except Exception as e:
            logger.error(f"Error in MissingMandatoryFieldsRule: {e}")


class BrokenRelationshipsRule(DataQualityRule):
    """Check for broken relationships (orphaned records)."""

    @property
    def rule_name(self) -> str:
        return "broken_relationships"

    @property
    def rule_description(self) -> str:
        return "Check for orphaned records and broken entity relationships"

    async def check(self) -> None:
        """Check for orphaned documents and assignments."""
        try:
            # This is a placeholder implementation
            # In production, would query actual models when they become available
            self.total_checked = 0
            self.issues = []
        except Exception as e:
            logger.error(f"Error in BrokenRelationshipsRule: {e}")


class ExpiredRecordsRule(DataQualityRule):
    """Check for expired contracts, permits, trainings, medicals, and PPE."""

    @property
    def rule_name(self) -> str:
        return "expired_records"

    @property
    def rule_description(self) -> str:
        return "Check for expired trainings, medicals, PPE, and contractor access"

    async def check(self) -> None:
        """Check for expired records."""
        try:
            # This is a placeholder implementation
            # In production, would check actual expiry dates in models
            self.total_checked = 0
            self.issues = []
        except Exception as e:
            logger.error(f"Error in ExpiredRecordsRule: {e}")


class DuplicateRecordsRule(DataQualityRule):
    """Check for potential duplicate records."""

    @property
    def rule_name(self) -> str:
        return "potential_duplicates"

    @property
    def rule_description(self) -> str:
        return "Check for potential duplicate employees or contractors"

    async def check(self) -> None:
        """Check for duplicate records."""
        try:
            # This is a placeholder implementation
            # In production, would query for duplicate emails, IDs, etc.
            self.total_checked = 0
            self.issues = []
        except Exception as e:
            logger.error(f"Error in DuplicateRecordsRule: {e}")


class DataQualityRuleEngine:
    """Engine for running data quality checks."""

    def __init__(self, tenant_id: str, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self.rules: list[type[DataQualityRule]] = [
            MissingMandatoryFieldsRule,
            BrokenRelationshipsRule,
            ExpiredRecordsRule,
            DuplicateRecordsRule,
        ]

    async def run_all_checks(self) -> tuple[list[DataQualityIssue], list[dict[str, Any]]]:
        """Run all rules and return issues + check results."""
        all_issues: list[DataQualityIssue] = []
        check_results: list[dict[str, Any]] = []

        tasks = []
        for rule_class in self.rules:
            rule = rule_class(self.tenant_id, self.db)
            tasks.append(self._run_rule(rule))

        results = await asyncio.gather(*tasks)
        for rule, issues, result in results:
            all_issues.extend(issues)
            check_results.append(result)

        return all_issues, check_results

    async def _run_rule(self, rule: DataQualityRule) -> tuple[DataQualityRule, list[DataQualityIssue], dict[str, Any]]:
        """Run a single rule and return results."""
        start = time.perf_counter()
        try:
            await rule.check()
        except Exception as e:
            logger.error(f"Error running rule {rule.rule_name}: {e}", exc_info=True)

        duration_ms = (time.perf_counter() - start) * 1000

        result = {
            "rule_name": rule.rule_name,
            "rule_description": rule.rule_description,
            "total_checked": rule.total_checked,
            "issues_found": len(rule.issues),
            "execution_time_ms": duration_ms,
        }

        return rule, rule.issues, result
