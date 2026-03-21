# TRAINING_AND_LMS

## Scope and current implementation status
Training/LMS remains a **partial-but-real foundation**, not a stub. The canonical backend code paths are:

- `backend/app/api/routes/training.py`
- `backend/app/api/routes/training_next.py`
- `backend/app/domains/training/service.py`
- `backend/app/modules/training/services.py`
- `backend/app/modules/briefings/services.py`
- `backend/app/models/models.py` (`TrainingPlan` and related entities)

Frontend training surfaces are expected under `frontend/src/pages/training/` and related route composition.

## Implemented production-minded foundations
- program / plan / assignment lifecycle foundations are present in the backend service layer;
- due-date and expiration tracking are already reflected in notifications/calendar touchpoints;
- briefing/training domain logic is covered by dedicated tests such as `backend/tests/test_briefings_service.py` and `backend/tests/test_next66_workflow_notifications_npa.py`;
- LMS/export-adjacent groundwork is represented by migrations such as `20260411_next66_lms_exports_machine_marketplace.py`.

## Hardening notes for this wave
- Notifications/calendar integration is now routed through `backend/app/modules/notifications/service.py`, so training due dates participate in a consistent application-service boundary rather than fat router logic.
- Acceptance and testing docs now explicitly map training assignment/completion scenarios to repo-local tests and commands.

## Remaining gaps
- SCORM/xAPI/proctoring are still foundation-only and should be treated as integration extension points, not feature-complete LMS parity.
- FRDO/EISOT export readiness is a domain foundation and needs additional acceptance-grade scenarios before production claims are widened.
- Learner/instructor UX should continue to be validated against actual frontend routes, because documentation is ahead of some route-level coverage.
