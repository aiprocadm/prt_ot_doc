import { lazy } from "react";

export const DocumentsPage = lazy(() => import("@/pages/documents/DocumentsPage"));
export const DocumentsWizardPage = lazy(() => import("@/pages/documents/DocumentsWizardPage"));
export const QuickGeneratePage = lazy(() => import("@/pages/documents/QuickGeneratePage"));
export const BrandingSettingsPage = lazy(() => import("@/pages/branding/BrandingSettingsPage"));
export const ApprovalsInboxPage = lazy(() => import("@/pages/approvals/ApprovalsInboxPage"));
export const ApprovalsOutboxPage = lazy(() => import("@/pages/approvals/ApprovalsOutboxPage"));
export const ApprovalRoutesPage = lazy(() => import("@/pages/approvals/ApprovalRoutesPage"));
export const SignaturesPage = lazy(() => import("@/pages/signatures/SignaturesPage"));
export const EdoPage = lazy(() => import("@/pages/edo/EdoPage"));
export const PipelineRunsPage = lazy(() => import("@/pages/PipelineRuns"));
export const PipelineRunDetailsPage = lazy(() => import("@/pages/PipelineRunDetails"));
export const PipelineBuilderPage = lazy(() => import("@/pages/PipelineBuilderPage"));
export const PackageProfilesPage = lazy(() => import("@/pages/packs/PackageProfilesPage"));
export const PackagePresetsPage = lazy(() => import("@/pages/packs/PackagePresetsPage"));
export const GeneratePackWizardPage = lazy(() => import("@/pages/packs/GeneratePackWizardPage"));
export const PackRunDetailsPage = lazy(() => import("@/pages/packs/PackRunDetailsPage"));
