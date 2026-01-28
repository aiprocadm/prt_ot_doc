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
    is_admin: false
  }
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
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, { status: "ready", company_id: "company-1" })
    ).toBe(true);
    expect(
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, { status: "draft", company_id: "company-1" })
    ).toBe(false);
    expect(
      ability.can(PERMISSIONS.DOCUMENT_EXPORT, { status: "ready", company_id: "company-2" })
    ).toBe(false);
  });

  it("проверяет правила для шаблонов", () => {
    const ability = buildAbility({ ...baseUser, roles: ["ot_pb_head"] });
    expect(
      ability.can(PERMISSIONS.TEMPLATE_EDIT, { template: { current_version: { status: "draft" } } })
    ).toBe(true);
    expect(
      ability.can(PERMISSIONS.TEMPLATE_EDIT, { template: { current_version: { status: "published" } } })
    ).toBe(false);
    expect(
      ability.can(PERMISSIONS.TEMPLATE_ACTIVATE, {
        template: { current_version: { id: "v1", status: "published" } },
        version: { id: "v2", status: "published" }
      })
    ).toBe(true);
  });
});
