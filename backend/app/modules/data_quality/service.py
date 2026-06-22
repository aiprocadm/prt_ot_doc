"""Data quality service for comprehensive data checks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .rules import DataQualityRuleEngine
from .schemas import DataQualityCheckResult, DataQualityIssue, DataQualityReport, IssueSeverity

logger = logging.getLogger("app.modules.data_quality")


class DataQualityService:
    """Service for running and reporting data quality checks."""

    def __init__(self, tenant_id: str, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self.engine = DataQualityRuleEngine(tenant_id, db)

    @staticmethod
    def _compute_completeness(total_checked: int, total_issues: int) -> float:
        """Rough completeness from rule coverage vs issues (bounded 0–100)."""
        if total_issues <= 0:
            return 100.0
        if total_checked <= 0:
            return max(5.0, round(100.0 - min(95.0, float(total_issues) * 6.0), 2))
        ratio = min(1.0, total_issues / max(float(total_checked), 1.0))
        return max(0.0, min(100.0, round(100.0 * (1.0 - ratio), 2)))

    async def run_comprehensive_check(self) -> DataQualityReport:
        """Run all data quality checks and return comprehensive report."""
        logger.info(f"Starting data quality check for tenant {self.tenant_id}")

        # Run all rules
        all_issues, check_results = await self.engine.run_all_checks()

        # Sort issues by severity (critical first)
        severity_order = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 1,
            IssueSeverity.MEDIUM: 2,
            IssueSeverity.LOW: 3,
        }
        all_issues.sort(key=lambda x: severity_order.get(x.severity, 999))

        # Calculate metrics
        total_issues = len(all_issues)
        total_checked = sum(int(r["total_checked"]) for r in check_results)
        completeness_percent = self._compute_completeness(total_checked, total_issues)

        # Count by severity
        severity_counts: dict[IssueSeverity, int] = {
            IssueSeverity.CRITICAL: 0,
            IssueSeverity.HIGH: 0,
            IssueSeverity.MEDIUM: 0,
            IssueSeverity.LOW: 0,
        }
        for issue in all_issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

        # Count by type
        issue_type_counts: dict[str, int] = {}
        for issue in all_issues:
            key = issue.issue_type.value
            issue_type_counts[key] = issue_type_counts.get(key, 0) + 1

        # Count by entity type
        entity_type_counts: dict[str, int] = {}
        for issue in all_issues:
            key = issue.affected_entity_type
            entity_type_counts[key] = entity_type_counts.get(key, 0) + 1

        # Convert check results to DTOs
        check_result_dtos = []
        for result in check_results:
            # Find issues for this rule
            rule_issues = [i for i in all_issues if i.id.startswith(result["rule_name"])]
            check_result_dtos.append(
                DataQualityCheckResult(
                    rule_name=result["rule_name"],
                    rule_description=result["rule_description"],
                    total_checked=result["total_checked"],
                    issues_found=result["issues_found"],
                    issues=rule_issues,
                    execution_time_ms=result["execution_time_ms"],
                )
            )

        # Build report
        report = DataQualityReport(
            tenant_id=self.tenant_id,
            completeness_percent=completeness_percent,
            total_issues=total_issues,
            critical_issues=severity_counts[IssueSeverity.CRITICAL],
            high_issues=severity_counts[IssueSeverity.HIGH],
            medium_issues=severity_counts[IssueSeverity.MEDIUM],
            low_issues=severity_counts[IssueSeverity.LOW],
            issue_breakdown=issue_type_counts,
            entity_breakdown=entity_type_counts,
            issues=all_issues[:20],  # Return top 20 issues
            check_results=check_result_dtos,
            generated_at=datetime.now(tz=timezone.utc),
        )

        logger.info(
            f"Data quality check completed: {total_issues} issues found, {completeness_percent:.1f}% complete"
        )

        return report

    async def get_issue_details(self, issue_id: str) -> DataQualityIssue | None:
        """Get details for a specific issue."""
        # Placeholder for future implementation
        return None

    async def mark_issue_reviewed(self, issue_id: str) -> bool:
        """Mark an issue as reviewed."""
        # Placeholder for future implementation
        return True

    async def get_issue_history(self, entity_id: str) -> list[DataQualityIssue]:
        """Get issue history for an entity."""
        # Placeholder for future implementation
        return []
