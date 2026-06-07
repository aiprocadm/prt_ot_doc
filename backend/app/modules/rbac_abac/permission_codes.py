MVP_PERMISSION_CODES: tuple[str, ...] = (
    "templates.read",
    "templates.write",
    "templates.delete",
    "documents.read",
    "documents.write",
    "documents.generate",
    "documents.sign",
    "documents.send_edo",
    "documents.export",
    "pipelines.run",
    "pipelines.read",
    "pipelines.cancel",
    "files.read",
    "files.write",
    "audit.read",
    "audit.export",
    "masterdata.read",
    "masterdata.write",
    "risk.read",
    "risk.write",
    "ppe.read",
    "ppe.write",
    "training.read",
    "training.write",
    "incidents.read",
    "incidents.write",
    "inspections.read",
    "inspections.write",
    "incidents.close",
    "incidents.approve",
    "investigations.read",
    "investigations.write",
    "investigations.approve",
    "inspections.approve",
    "inspection_plans.read",
    "inspection_plans.write",
    "inspection_checklists.read",
    "inspection_checklists.write",
    "inspection_checklists.activate",
    "findings.read",
    "findings.write",
    "findings.verify",
    "prescriptions.read",
    "prescriptions.write",
    "prescriptions.verify",
    "corrective_actions.read",
    "corrective_actions.write",
    "corrective_actions.verify",
    "inspection_prep.read",
    "inspection_prep.write",
    "inspection_prep.export",
    "inspection_prep.send_edo",
    "reports.incidents.export",
    "reports.inspections.export",
    "reports.capa.export",
    "billing.read",
    "admin.tenants",
    "admin.settings",
    "admin.roles",
)

# Module-level access control (vNext-SEC-01)
MODULE_PERMISSIONS: tuple[str, ...] = (
    "modules.risk",
    "modules.ppe",
    "modules.training",
    "modules.medical",
    "modules.incidents",
    "modules.inspections",
    "modules.documents",
    "modules.tasks",
    "modules.templates",
    "modules.audit",
    "modules.admin",
    "modules.branding",
    "modules.masterdata",
    "modules.billing",
    "modules.contractors",
    "modules.compliance",
    "modules.briefings",
    "modules.sout",
)

# Default modules per role (for filtering UI navigation)
ROLE_MODULE_DEFAULTS: dict[str, list[str]] = {
    "owner": [
        "risk", "ppe", "training", "medical", "incidents", "inspections",
        "documents", "tasks", "templates", "audit", "admin", "branding",
        "masterdata", "billing", "contractors", "compliance", "briefings", "sout"
    ],
    "admin": [
        "risk", "ppe", "training", "medical", "incidents", "inspections",
        "documents", "tasks", "templates", "audit", "admin", "branding",
        "masterdata", "contractors", "compliance"
    ],
    "ot_pb_lead": [
        "risk", "ppe", "incidents", "inspections", "documents", "tasks", "contractors"
    ],
    "ot_specialist": [
        "risk", "ppe", "incidents", "documents", "tasks"
    ],
    "hr": [
        "training", "medical", "masterdata", "documents", "tasks"
    ],
    "teacher": [
        "training", "briefings", "documents"
    ],
    "student": [
        "training", "documents"
    ],
    "manager": [
        "tasks", "documents", "incidents"
    ],
    "worker": [
        "tasks", "documents"
    ],
    "auditor_ro": [
        "audit", "documents", "risk", "incidents", "compliance"
    ],
}
