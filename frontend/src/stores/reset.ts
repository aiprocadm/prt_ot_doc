import { useAuditStore } from "@/stores/audit";
import { useCompaniesStore } from "@/stores/companies";
import { useDocumentsStore } from "@/stores/documents";
import { useFilesStore } from "@/stores/files";
import { useNpaStore } from "@/stores/npa";
import { usePacksStore } from "@/stores/packs";
import { usePersonsStore } from "@/stores/persons";
import { useRiskStore } from "@/stores/risk";
import { useTasksStore } from "@/stores/tasks";
import { useTemplatesStore } from "@/stores/templates";

export const resetTenantStores = () => {
  useAuditStore.getState().reset();
  useCompaniesStore.getState().reset();
  useDocumentsStore.getState().reset();
  useFilesStore.getState().reset();
  useNpaStore.getState().reset();
  usePacksStore.getState().reset();
  usePersonsStore.getState().reset();
  useRiskStore.getState().reset();
  useTasksStore.getState().reset();
  useTemplatesStore.getState().reset();
};
