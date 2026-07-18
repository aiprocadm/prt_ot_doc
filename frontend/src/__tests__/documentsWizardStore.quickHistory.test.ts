import { describe, expect, it } from "vitest";

import { useDocumentsWizardStore } from "@/stores/documentsWizard";

describe("documentsWizard quick history", () => {
  it("keeps unique quick-generation entries and caps list size", () => {
    useDocumentsWizardStore.getState().reset();
    const { pushQuickGenerationHistory } = useDocumentsWizardStore.getState();

    for (let index = 0; index < 12; index += 1) {
      const id = index === 11 ? "run-1" : `run-${index}`;
      pushQuickGenerationHistory({
        id,
        createdAt: new Date().toISOString(),
        personId: `person-${index}`,
        companyId: "company-1",
        siteId: "",
        caseType: "employment",
        templateCode: "order-template",
        templateVersion: 1,
        taskId: id,
        status: "queued",
      });
    }

    const entries = useDocumentsWizardStore.getState().quickGenerationHistory;
    expect(entries.length).toBe(10);
    expect(new Set(entries.map((item) => item.id)).size).toBe(entries.length);
  });
});
