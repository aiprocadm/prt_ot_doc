import { describe, expect, it } from "vitest";

import { buildAbility } from "@/permissions/ability";
import { PERMISSIONS } from "@/permissions/permissions";
import type { UserDto } from "@/types/dto/auth";

const baseUser: UserDto = {
  id: "user-1",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "user@example.com",
  full_name: "User",
  roles: ["ot_specialist"],
  permissions: [],
  attributes: {
    tenant_id: "tenant-1",
    company_ids: ["company-1"],
    site_ids: ["site-1"],
    is_admin: false,
  },
};

describe("buildAbility", () => {
  it("разрешает доступ по роли", () => {
    const ability = buildAbility(baseUser);
    expect(ability.can(PERMISSIONS.DOCUMENT_VIEW)).toBe(true);
    expect(ability.can(PERMISSIONS.ADMIN_MANAGE_ROLES)).toBe(false);
  });

  it("учитывает атрибуты компании и статуса", () => {
    const ability = buildAbility(baseUser);
    expect(
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, {
        status: "ready",
        company_id: "company-1",
      }),
    ).toBe(true);
    expect(
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, {
        status: "draft",
        company_id: "company-1",
      }),
    ).toBe(false);
    expect(
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, {
        status: "ready",
        company_id: "company-2",
      }),
    ).toBe(false);
  });

  it("проверяет правила для шаблонов", () => {
    const ability = buildAbility({ ...baseUser, roles: ["ot_pb_head"] });
    expect(
      ability.can(PERMISSIONS.TEMPLATE_EDIT, {
        template: { current_version: { status: "draft" } },
      }),
    ).toBe(true);
    expect(
      ability.can(PERMISSIONS.TEMPLATE_EDIT, {
        template: { current_version: { status: "published" } },
      }),
    ).toBe(false);
    expect(
      ability.can(PERMISSIONS.TEMPLATE_ACTIVATE, {
        template: { current_version: { id: "v1", status: "published" } },
        version: { id: "v2", status: "published" },
      }),
    ).toBe(true);
  });

  it("нормализует алиасы ролей и прав", () => {
    const byRole = buildAbility({
      ...baseUser,
      roles: ["auditor"],
      permissions: [],
    });
    expect(byRole.can(PERMISSIONS.AUDIT_VIEW)).toBe(true);
    expect(byRole.can(PERMISSIONS.DOCUMENT_CREATE)).toBe(false);

    const byPermission = buildAbility({
      ...baseUser,
      roles: [],
      permissions: ["integrations.read", "warehouse.read"],
    });
    expect(byPermission.can(PERMISSIONS.INTEGRATIONS_VIEW)).toBe(true);
    expect(byPermission.can(PERMISSIONS.WAREHOUSE_VIEW)).toBe(true);
  });

  it("открывает Data Quality для ролей, согласованных с backend RBAC", () => {
    const owner = buildAbility({
      ...baseUser,
      roles: ["owner"],
      permissions: [],
    });
    expect(owner.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);

    const admin = buildAbility({
      ...baseUser,
      roles: ["admin"],
      permissions: [],
    });
    expect(admin.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);

    const otHead = buildAbility({
      ...baseUser,
      roles: ["ot_pb_head"],
      permissions: [],
    });
    expect(otHead.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);

    const otLead = buildAbility({
      ...baseUser,
      roles: ["ot_pb_lead"],
      permissions: [],
    });
    expect(otLead.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);

    const hr = buildAbility({ ...baseUser, roles: ["hr"], permissions: [] });
    expect(hr.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);

    const lineManager = buildAbility({
      ...baseUser,
      roles: ["line_manager"],
      permissions: [],
    });
    expect(lineManager.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(true);
  });

  it("закрывает Data Quality для ролей вне backend RBAC", () => {
    const worker = buildAbility({
      ...baseUser,
      roles: ["worker"],
      permissions: [],
    });
    expect(worker.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(false);

    const student = buildAbility({
      ...baseUser,
      roles: ["student"],
      permissions: [],
    });
    expect(student.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(false);

    const otSpecialist = buildAbility({
      ...baseUser,
      roles: ["ot_specialist"],
      permissions: [],
    });
    expect(otSpecialist.can(PERMISSIONS.DATA_QUALITY_VIEW)).toBe(false);
  });

  it("открывает Smart Calendar для HSE-ролей, согласованных с backend _CALENDAR_READ_ROLES", () => {
    const owner = buildAbility({
      ...baseUser,
      roles: ["owner"],
      permissions: [],
    });
    expect(owner.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const admin = buildAbility({
      ...baseUser,
      roles: ["admin"],
      permissions: [],
    });
    expect(admin.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const otHead = buildAbility({
      ...baseUser,
      roles: ["ot_pb_head"],
      permissions: [],
    });
    expect(otHead.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const hr = buildAbility({ ...baseUser, roles: ["hr"], permissions: [] });
    expect(hr.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const lineManager = buildAbility({
      ...baseUser,
      roles: ["line_manager"],
      permissions: [],
    });
    expect(lineManager.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const otSpecialist = buildAbility({
      ...baseUser,
      roles: ["ot_specialist"],
      permissions: [],
    });
    expect(otSpecialist.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const pbEngineer = buildAbility({
      ...baseUser,
      roles: ["pb_engineer"],
      permissions: [],
    });
    expect(pbEngineer.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);

    const ecologist = buildAbility({
      ...baseUser,
      roles: ["ecologist"],
      permissions: [],
    });
    expect(ecologist.can(PERMISSIONS.CALENDAR_VIEW)).toBe(true);
  });

  it("закрывает Smart Calendar для ролей вне HSE-набора", () => {
    const worker = buildAbility({
      ...baseUser,
      roles: ["worker"],
      permissions: [],
    });
    expect(worker.can(PERMISSIONS.CALENDAR_VIEW)).toBe(false);

    const student = buildAbility({
      ...baseUser,
      roles: ["student"],
      permissions: [],
    });
    expect(student.can(PERMISSIONS.CALENDAR_VIEW)).toBe(false);

    const client = buildAbility({
      ...baseUser,
      roles: ["client"],
      permissions: [],
    });
    expect(client.can(PERMISSIONS.CALENDAR_VIEW)).toBe(false);
  });
});
