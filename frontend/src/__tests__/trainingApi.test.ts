import MockAdapter from "axios-mock-adapter";
import { describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { getLearnerDashboard, getTeacherDashboard, getTrainingProgramDetail, getTrainingPrograms } from "@/api/training";
import { tenantStorage } from "@/api/tenantStorage";

describe("training api", () => {
  it("loads teacher and learner dashboards via service layer", async () => {
    tenantStorage.setTenant({ slug: "demo" });
    const mock = new MockAdapter(apiClient);

    mock.onGet("/training/teacher/dashboard").reply(200, {
      groups_total: 3,
      enrollments_total: 10,
      completed_total: 5,
      average_progress_percent: 60
    });
    mock.onGet("/training/learner/dashboard").reply(200, {
      assigned_total: 7,
      completed_total: 4,
      overdue_total: 1
    });

    await expect(getTeacherDashboard()).resolves.toMatchObject({ groups_total: 3 });
    await expect(getLearnerDashboard()).resolves.toMatchObject({ assigned_total: 7 });

    mock.restore();
  });

  it("loads program list and detail", async () => {
    tenantStorage.setTenant({ slug: "demo" });
    const mock = new MockAdapter(apiClient);

    mock.onGet("/training/programs").reply(200, { items: [{ id: "program-1" }] });
    mock.onGet("/training/programs/program-1/detail").reply(200, {
      modules: [{ module: { id: "m1", title: "Module 1" }, lessons: [{ id: "l1", title: "Lesson 1" }] }]
    });

    const programs = await getTrainingPrograms();
    const detail = await getTrainingProgramDetail(programs.items[0]!.id);

    expect(detail.modules[0]?.module.title).toBe("Module 1");
    mock.restore();
  });
});

