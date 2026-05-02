"""Data quality rules and rule engine."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.models import (
    EmploymentStatus,
    MedicalExam,
    Person,
    Site,
    Training,
    TrainingStatus,
    Workplace,
)

from .schemas import DataQualityIssue, IssueSeverity, IssueType

logger = logging.getLogger("app.modules.data_quality")


def _is_blank(value: str | None) -> bool:
    return value is None or not str(value).strip()


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
        raise NotImplementedError

    @property
    @abstractmethod
    def rule_description(self) -> str:
        """Human-readable rule description."""
        raise NotImplementedError

    @abstractmethod
    async def check(self) -> None:
        """Run the rule check. Must populate self.issues and self.total_checked."""
        raise NotImplementedError


class MissingMandatoryFieldsRule(DataQualityRule):
    """Check for missing mandatory fields in critical entities (Person, Site)."""

    @property
    def rule_name(self) -> str:
        return "missing_mandatory_fields"

    @property
    def rule_description(self) -> str:
        return "Check for missing mandatory fields in employees (person), and sites"

    async def check(self) -> None:
        self.issues = []
        try:
            stmt = select(Person).where(
                Person.tenant_id == self.tenant_id,
                Person.deleted_at.is_(None),
            )
            rows = (await self.db.execute(stmt)).scalars().all()
            self.total_checked = len(rows)

            for person in rows:
                missing_fields: list[str] = []

                if _is_blank(person.first_name):
                    missing_fields.append("first_name")
                if _is_blank(person.last_name):
                    missing_fields.append("last_name")

                if person.employment_status == EmploymentStatus.ACTIVE and _is_blank(
                    getattr(person, "email", None)
                ):
                    missing_fields.append("email")

                if person.employment_status == EmploymentStatus.ACTIVE and not getattr(
                    person, "position_id", None
                ):
                    missing_fields.append("position_id")

                if not missing_fields:
                    continue

                severity = IssueSeverity.MEDIUM
                critical_names = {"first_name", "last_name", "email"}
                if critical_names.intersection(set(missing_fields)):
                    severity = IssueSeverity.HIGH

                display = (
                    " ".join(
                        p for p in (person.first_name or "", person.last_name or "") if p.strip()
                    ).strip()
                    or "(unnamed)"
                )

                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:person:{person.id}:{'-'.join(sorted(missing_fields))}",
                        issue_type=IssueType.MISSING_FIELD,
                        severity=severity,
                        title=f"person {person.id}: missing {', '.join(missing_fields)}",
                        description="Mandatory or recommended HR/OT master fields are empty.",
                        affected_entity_type="person",
                        affected_entity_id=str(person.id),
                        affected_entity_name=display[:255],
                        additional_info={"missing_fields": missing_fields},
                    )
                )

            site_stmt = select(Site).where(
                Site.tenant_id == self.tenant_id,
                Site.deleted_at.is_(None),
            )
            sites = (await self.db.execute(site_stmt)).scalars().all()
            self.total_checked += len(sites)

            for site in sites:
                if not _is_blank(site.name):
                    continue
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:site:{site.id}:missing_name",
                        issue_type=IssueType.MISSING_FIELD,
                        severity=IssueSeverity.CRITICAL,
                        title=f"site {site.id}: missing name",
                        description="Site records must include a readable name.",
                        affected_entity_type="site",
                        affected_entity_id=str(site.id),
                        affected_entity_name=None,
                        additional_info={"missing_fields": ["name"]},
                    )
                )
        except Exception as e:
            logger.exception("missing_mandatory_fields rule failed: %s", e)


class BrokenRelationshipsRule(DataQualityRule):
    """Check for broken references (documents → person, workplaces → site)."""

    @property
    def rule_name(self) -> str:
        return "broken_relationships"

    @property
    def rule_description(self) -> str:
        return "Detect documents linked to removed persons and workplaces linked to missing sites"

    async def check(self) -> None:
        self.issues = []
        try:
            doc_stmt = (
                select(Document.id, Document.person_id)
                .outerjoin(Person, Document.person_id == Person.id)
                .where(
                    Document.tenant_id == self.tenant_id,
                    Document.person_id.is_not(None),
                    or_(Person.id.is_(None), Person.deleted_at.is_not(None)),
                )
            )
            doc_rows = (await self.db.execute(doc_stmt)).all()
            self.total_checked += len(doc_rows)

            for doc_id, person_id in doc_rows:
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:document:{doc_id}:person:{person_id}",
                        issue_type=IssueType.BROKEN_RELATIONSHIP,
                        severity=IssueSeverity.HIGH,
                        title=f"document {doc_id} references invalid person",
                        description="Document.person_id points to a deleted or missing person.",
                        affected_entity_type="document",
                        affected_entity_id=str(doc_id),
                        additional_info={"person_id": str(person_id)},
                    )
                )

            wp_stmt = (
                select(Workplace.id, Workplace.site_id)
                .outerjoin(Site, Workplace.site_id == Site.id)
                .where(
                    Workplace.tenant_id == self.tenant_id,
                    Workplace.deleted_at.is_(None),
                    Workplace.site_id.is_not(None),
                    or_(Site.id.is_(None), Site.deleted_at.is_not(None)),
                )
            )
            wp_rows = (await self.db.execute(wp_stmt)).all()
            self.total_checked += len(wp_rows)

            for wp_id, site_id in wp_rows:
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:workplace:{wp_id}:site:{site_id}",
                        issue_type=IssueType.BROKEN_RELATIONSHIP,
                        severity=IssueSeverity.MEDIUM,
                        title=f"workplace {wp_id} references invalid site",
                        description="Workplace.site_id points to a missing or deleted site.",
                        affected_entity_type="workplace",
                        affected_entity_id=str(wp_id),
                        additional_info={"site_id": str(site_id)},
                    )
                )
        except Exception as e:
            logger.exception("broken_relationships rule failed: %s", e)


class ExpiredRecordsRule(DataQualityRule):
    """Expired medical exams and trainings (by valid_until / expires_at)."""

    @property
    def rule_name(self) -> str:
        return "expired_records"

    @property
    def rule_description(self) -> str:
        return "Medical exams past valid_until and trainings past expires_at"

    async def check(self) -> None:
        self.issues = []
        today = date.today()
        now = datetime.now(tz=timezone.utc)
        try:
            mex_stmt = select(MedicalExam).where(
                MedicalExam.tenant_id == self.tenant_id,
                MedicalExam.deleted_at.is_(None),
                MedicalExam.valid_until < today,
            )
            exams = (await self.db.execute(mex_stmt)).scalars().all()
            self.total_checked += len(exams)

            for exam in exams:
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:medical_exam:{exam.id}",
                        issue_type=IssueType.EXPIRED_RECORD,
                        severity=IssueSeverity.HIGH,
                        title=f"medical exam {exam.id} expired",
                        description=f"Valid until was {exam.valid_until.isoformat()}",
                        affected_entity_type="medical_exam",
                        affected_entity_id=str(exam.id),
                        additional_info={
                            "person_id": str(exam.person_id),
                            "valid_until": exam.valid_until.isoformat(),
                        },
                    )
                )

            tr_stmt = select(Training).where(
                Training.tenant_id == self.tenant_id,
                Training.expires_at.is_not(None),
                Training.expires_at < now,
                Training.status == TrainingStatus.COMPLETED,
            )
            trainings = (await self.db.execute(tr_stmt)).scalars().all()
            self.total_checked += len(trainings)

            for tr in trainings:
                exp = tr.expires_at
                exp_s = exp.isoformat() if exp else ""
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:training:{tr.id}",
                        issue_type=IssueType.EXPIRED_RECORD,
                        severity=IssueSeverity.MEDIUM,
                        title=f"training {tr.id} certificate expired",
                        description=f"expires_at was {exp_s}",
                        affected_entity_type="training",
                        affected_entity_id=str(tr.id),
                        additional_info={"person_id": str(tr.person_id), "expires_at": exp_s},
                    )
                )
        except Exception as e:
            logger.exception("expired_records rule failed: %s", e)


class DuplicateRecordsRule(DataQualityRule):
    """Duplicate person emails within a tenant (case-insensitive)."""

    @property
    def rule_name(self) -> str:
        return "potential_duplicates"

    @property
    def rule_description(self) -> str:
        return "Duplicate person emails sharing the same normalised address"

    async def check(self) -> None:
        self.issues = []
        try:
            norm = func.lower(func.trim(Person.email))
            stmt = (
                select(norm.label("norm_email"), func.count(Person.id))
                .where(
                    Person.tenant_id == self.tenant_id,
                    Person.deleted_at.is_(None),
                    Person.email.is_not(None),
                    func.trim(Person.email) != "",
                )
                .group_by(norm)
                .having(func.count(Person.id) > 1)
            )
            rows = (await self.db.execute(stmt)).all()
            self.total_checked += len(rows)

            for norm_email, _cnt in rows:
                if norm_email is None:
                    continue
                email_display = str(norm_email)
                self.issues.append(
                    DataQualityIssue(
                        id=f"{self.rule_name}:person:email:{email_display}",
                        issue_type=IssueType.DUPLICATE,
                        severity=IssueSeverity.MEDIUM,
                        title=f'Duplicate email "{email_display}"',
                        description="Multiple persons share the same normalised email address.",
                        affected_entity_type="person",
                        affected_entity_id=email_display[:128],
                        additional_info={"duplicate_email": email_display},
                    )
                )
        except Exception as e:
            logger.exception("potential_duplicates rule failed: %s", e)


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

    async def _run_rule(
        self, rule: DataQualityRule
    ) -> tuple[DataQualityRule, list[DataQualityIssue], dict[str, Any]]:
        """Run a single rule and return results."""
        start = time.perf_counter()
        try:
            await rule.check()
        except Exception as e:
            logger.error("Error running rule %s: %s", rule.rule_name, e, exc_info=True)

        duration_ms = (time.perf_counter() - start) * 1000

        result = {
            "rule_name": rule.rule_name,
            "rule_description": rule.rule_description,
            "total_checked": rule.total_checked,
            "issues_found": len(rule.issues),
            "execution_time_ms": duration_ms,
        }

        return rule, rule.issues, result
