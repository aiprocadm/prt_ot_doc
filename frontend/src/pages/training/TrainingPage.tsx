import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/api/client";
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

  useEffect(() => {
    void apiClient.get<TeacherDashboard>("/training/teacher/dashboard").then(({ data }) => setTeacher(data)).catch(() => undefined);
    void apiClient.get<LearnerDashboard>("/training/learner/dashboard", { params: { person_id: "me" } }).then(({ data }) => setLearner(data)).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: t("training.title") }]} />
      <Tabs defaultValue="teacher" aria-label={t("training.title")}>
        <TabsList>
          <TabsTrigger value="teacher">{t("training.teacherView")}</TabsTrigger>
          <TabsTrigger value="learner">{t("training.learnerView")}</TabsTrigger>
        </TabsList>
        <TabsContent value="teacher" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard title="Группы" value={teacher?.groups_total ?? 0} />
            <StatCard title="Назначения" value={teacher?.enrollments_total ?? 0} />
            <StatCard title="Средний прогресс" value={`${teacher?.average_progress_percent ?? 0}%`} />
          </div>
        </TabsContent>
        <TabsContent value="learner" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard title="Назначено" value={learner?.assigned_total ?? 0} />
            <StatCard title="Завершено" value={learner?.completed_total ?? 0} />
            <StatCard title="Просрочено" value={learner?.overdue_total ?? 0} />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>{t("training.completion")}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              SCORM/xAPI/proctoring-ready progress ingestion is available through backend contracts and reflected in learner completion statuses.
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default TrainingPage;
