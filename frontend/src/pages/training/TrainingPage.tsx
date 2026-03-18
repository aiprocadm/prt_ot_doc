import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type TeacherDashboard = {
  groups_total: number;
  enrollments_total: number;
  completed_total: number;
  average_progress_percent: number;
};

type LearnerDashboard = {
  assigned_total: number;
  completed_total: number;
  overdue_total: number;
  next_due_at?: string | null;
  items?: Array<{ id: string; completion_status: string; progress_percent: number; due_at?: string | null }>;
};

const StatCard = ({ title, value }: { title: string; value: number | string }) => (
  <Card>
    <CardHeader className="pb-2">
      <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
    </CardHeader>
    <CardContent>
      <div className="text-2xl font-semibold">{value}</div>
    </CardContent>
  </Card>
);

const TrainingPage = () => {
  const { t } = useTranslation();
  const [teacher, setTeacher] = useState<TeacherDashboard | null>(null);
  const [learner, setLearner] = useState<LearnerDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [programDetail, setProgramDetail] = useState<{ modules: Array<{ module: { id: string; title: string }; lessons: Array<{ id: string; title: string }> }> } | null>(null);

  useEffect(() => {
    void apiClient.get<TeacherDashboard>("/training/teacher/dashboard").then(({ data }) => setTeacher(data)).catch(() => setError("teacher"));
    void apiClient.get<LearnerDashboard>("/training/learner/dashboard", { params: { person_id: "me" } }).then(({ data }) => setLearner(data)).catch(() => setError("learner"));
    void apiClient.get<{ items: Array<{ id: string }> }>("/training/programs").then(({ data }) => {
      const firstProgram = data.items?.[0]?.id;
      if (firstProgram) {
        return apiClient.get(`/training/programs/${firstProgram}/detail`).then(({ data: detail }) => setProgramDetail(detail));
      }
      return undefined;
    }).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: t("common.home"), to: "/dashboard" }, { label: t("training.title") }]} />
      <Tabs defaultValue="teacher" aria-label={t("training.title")}>
        <TabsList>
          <TabsTrigger value="teacher">{t("training.teacherView")}</TabsTrigger>
          <TabsTrigger value="learner">{t("training.learnerView")}</TabsTrigger>
        </TabsList>
        <TabsContent value="teacher" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard title={t("training.groups")} value={teacher?.groups_total ?? 0} />
            <StatCard title={t("training.enrollments")} value={teacher?.enrollments_total ?? 0} />
            <StatCard title={t("training.averageProgress")} value={`${teacher?.average_progress_percent ?? 0}%`} />
          </div>
          {programDetail?.modules?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("training.lessonStructure")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {programDetail.modules.map((entry) => (
                  <div key={entry.module.id} className="rounded-md border p-3">
                    <div className="font-medium">{entry.module.title}</div>
                    <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
                      {entry.lessons.map((lesson) => <li key={lesson.id}>{lesson.title}</li>)}
                    </ul>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : <EmptyState title={t("training.lessonStructure")} description={t("training.noSchedule")} />}
        </TabsContent>
        <TabsContent value="learner" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard title={t("training.assigned")} value={learner?.assigned_total ?? 0} />
            <StatCard title={t("training.completed")} value={learner?.completed_total ?? 0} />
            <StatCard title={t("training.overdue")} value={learner?.overdue_total ?? 0} />
          </div>
          {learner?.items?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("training.materials")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm" aria-live="polite">
                  {learner.items.slice(0, 5).map((item) => (
                    <li key={item.id} className="rounded-md border p-3">
                      <div className="font-medium">{item.completion_status}</div>
                      <div className="text-muted-foreground">{item.progress_percent}% · {item.due_at ?? t("training.noSchedule")}</div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>{t("training.completion")}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              {t("training.learnerHint")}
            </CardContent>
          </Card>
          {learner?.next_due_at ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("training.nextDue")}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">{learner.next_due_at}</CardContent>
            </Card>
          ) : null}
          {error ? <EmptyState title="Training API" description={error} /> : null}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default TrainingPage;
