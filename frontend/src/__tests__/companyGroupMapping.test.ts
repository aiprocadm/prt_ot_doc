import { describe, expect, it } from "vitest";

import { buildCompanyWriteBody, normalizeCompanyRead } from "@/api/companiesApi";
import type { CompanyFormValues } from "@/types/forms/companies";

/**
 * BIZ-53 (разд. 53.3): группа компаний — головная компания в форме и в чтении.
 *
 * Главная ловушка маппера: пустой выбор «Без группы» обязан уезжать на бэкенд
 * как null (снятие привязки), а НЕ как пустая строка (бэкенд отверг бы её
 * длиной) и НЕ пропадать из тела (exclude_unset не снял бы привязку никогда).
 */

const baseForm: CompanyFormValues = {
  name: "ООО Тест",
  inn: "",
  kpp: "",
  ogrn: "",
  address: "",
  email: "",
  phone: "",
  website: "",
  status: "active",
  tags: [],
  parent_company_id: "",
};

describe("группа компаний: маппинг формы и чтения", () => {
  it("выбранная головная уезжает своим id", () => {
    const body = buildCompanyWriteBody({
      ...baseForm,
      parent_company_id: "parent-1",
    });
    expect(body.parent_company_id).toBe("parent-1");
  });

  it("пустой выбор «Без группы» уезжает null — это снятие привязки", () => {
    const body = buildCompanyWriteBody(baseForm);
    expect(body.parent_company_id).toBeNull();
  });

  it("чтение проносит parent_company_id до карточки", () => {
    const dto = normalizeCompanyRead({
      id: "c-1",
      name: "Дочка",
      parent_company_id: "parent-1",
    });
    expect(dto.parent_company_id).toBe("parent-1");
    expect(
      normalizeCompanyRead({ id: "c-2", name: "Одиночка" }).parent_company_id,
    ).toBeNull();
  });
});
