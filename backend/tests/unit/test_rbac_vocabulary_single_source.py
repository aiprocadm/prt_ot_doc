from app.core import rbac_abac as core_rbac
from app.modules.rbac_abac import rules as module_rules


def test_role_permissions_has_single_source_of_truth() -> None:
    assert module_rules.ROLE_PERMISSIONS is core_rbac.ROLE_PERMISSIONS
    assert module_rules.RESOURCE_PERMISSIONS is core_rbac.RESOURCE_PERMISSIONS
