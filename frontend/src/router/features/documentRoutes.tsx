import type { ReactElement } from "react";
import { Route } from "react-router-dom";

import {
  ApprovalRoutesPage,
  ApprovalsInboxPage,
  ApprovalsOutboxPage,
  BrandingSettingsPage,
  DocumentsPage,
  DocumentsWizardPage,
  EdoPage,
  GeneratePackWizardPage,
  PackagePresetsPage,
  PackageProfilesPage,
  PackRunDetailsPage,
  PipelineBuilderPage,
  PipelineRunDetailsPage,
  PipelineRunsPage,
  SignaturesPage,
} from "@/router/pageRegistry";

export const documentReadRoutes = (): ReactElement[] => [
  <Route key="/documents" path="/documents" element={<DocumentsPage />} />,
  <Route key="/documents/branding" path="/documents/branding" element={<BrandingSettingsPage />} />,
  <Route key="/approvals/inbox" path="/approvals/inbox" element={<ApprovalsInboxPage />} />,
  <Route key="/approvals/outbox" path="/approvals/outbox" element={<ApprovalsOutboxPage />} />,
  <Route key="/approval-routes" path="/approval-routes" element={<ApprovalRoutesPage />} />,
  <Route key="/signatures" path="/signatures" element={<SignaturesPage />} />,
  <Route key="/edo" path="/edo" element={<EdoPage />} />,
  <Route key="/pipelines/profiles" path="/pipelines/profiles" element={<PipelineBuilderPage />} />,
  <Route key="/pipelines/runs" path="/pipelines/runs" element={<PipelineRunsPage />} />,
  <Route key="/pipelines/runs/:id" path="/pipelines/runs/:id" element={<PipelineRunDetailsPage />} />,
  <Route key="/jobs" path="/jobs" element={<PipelineRunsPage />} />,
  <Route key="/jobs/:id" path="/jobs/:id" element={<PipelineRunDetailsPage />} />,
  <Route key="/package-profiles" path="/package-profiles" element={<PackageProfilesPage />} />,
  <Route key="/package-presets" path="/package-presets" element={<PackagePresetsPage />} />,
  <Route key="/generate-pack/:presetId" path="/generate-pack/:presetId" element={<GeneratePackWizardPage />} />,
  <Route key="/pack-runs/:id" path="/pack-runs/:id" element={<PackRunDetailsPage />} />,
];

export const documentCreateRoutes = (): ReactElement[] => [
  <Route key="/documents/wizard" path="/documents/wizard" element={<DocumentsWizardPage />} />,
  <Route key="/generation" path="/generation" element={<DocumentsWizardPage />} />,
];
