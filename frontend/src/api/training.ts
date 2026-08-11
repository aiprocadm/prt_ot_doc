import { apiClient } from "@/api/client";

export type TeacherDashboardDto = {
  groups_total: number;
  enrollments_total: number;
  completed_total: number;
  average_progress_percent: number;
};

export type LearnerDashboardDto = {
  assigned_total: number;
  completed_total: number;
  overdue_total: number;
  next_due_at?: string | null;
  items?: Array<{ id: string; completion_status: string; progress_percent: number; due_at?: string | null }>;
};

export type TrainingAnalyticsDto = {
  completed_total: number;
  retake_total: number;
  average_attempt_score: number;
  material_types: Record<string, number>;
};

export type TrainingProgramDetailDto = {
  modules: Array<{ module: { id: string; title: string }; lessons: Array<{ id: string; title: string }> }>;
};

export const getTeacherDashboard = async (): Promise<TeacherDashboardDto> => {
  const { data } = await apiClient.get<TeacherDashboardDto>("/training/teacher/dashboard");
  return data;
};

export const getTrainingAnalytics = async (): Promise<TrainingAnalyticsDto> => {
  const { data } = await apiClient.get<TrainingAnalyticsDto>("/training/analytics/overview");
  return data;
};

export const getTrainingPrograms = async (): Promise<{ items: Array<{ id: string }> }> => {
  const { data } = await apiClient.get<{ items: Array<{ id: string }> }>("/training/programs");
  return data;
};

export const getTrainingProgramDetail = async (programId: string): Promise<TrainingProgramDetailDto> => {
  const { data } = await apiClient.get<TrainingProgramDetailDto>(`/training/programs/${programId}/detail`);
  return data;
};

export const getLearnerDashboard = async (): Promise<LearnerDashboardDto> => {
  const { data } = await apiClient.get<LearnerDashboardDto>("/training/learner/dashboard", { params: { person_id: "me" } });
  return data;
};

