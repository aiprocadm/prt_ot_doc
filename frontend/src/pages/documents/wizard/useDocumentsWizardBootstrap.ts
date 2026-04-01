import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getDocumentBatch } from "@/api/documents";
import { getBrandingProfile, listLayoutPresets, listSites, type LayoutPresetDto, type SiteDto } from "@/api/branding";
import { getPipelineRun } from "@/api/pipelines";
import { useCompaniesStore } from "@/stores/companies";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";
import { useTenantStore } from "@/stores/tenant";

export const useDocumentsWizardBootstrap = () => {
  const tenant = useTenantStore((s) => s.tenant);
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const { companyId, siteId, headerPreset, taskId, batch, pipelineRun, setPartial } = useDocumentsWizardStore();

  const [sites, setSites] = useState<SiteDto[]>([]);
  const [layoutPresets, setLayoutPresets] = useState<LayoutPresetDto[]>([]);
  const [brandingProfileScope, setBrandingProfileScope] = useState<string>("company");

  useEffect(() => {
    listCompanies().catch(() => undefined);
    listLayoutPresets().then(setLayoutPresets).catch(() => undefined);
  }, [listCompanies]);

  useEffect(() => {
    if (!companyId && companies.length > 0) {
      setPartial({ companyId: companies[0].id });
    }
  }, [companies, companyId, setPartial]);

  useEffect(() => {
    if (!companyId) {
      setSites([]);
      return;
    }
    listSites(companyId)
      .then(setSites)
      .catch(() => setSites([]));

    getBrandingProfile(companyId, siteId || undefined)
      .then((profile) => {
        setBrandingProfileScope(profile.scope);
        const nextPreset = headerPreset || profile.preferred_header_preset_code || "";
        if (nextPreset !== headerPreset) {
          setPartial({ headerPreset: nextPreset });
        }
      })
      .catch(() => undefined);
  }, [companyId, headerPreset, setPartial, siteId]);

  useEffect(() => {
    if (!taskId || !tenant) return;
    if (pipelineRun && !["queued", "running"].includes(pipelineRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const run = await getPipelineRun(taskId);
        setPartial({ pipelineRun: run });
      } catch {
        toast.error("Не удалось обновить timeline job.");
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [pipelineRun, setPartial, taskId, tenant]);

  useEffect(() => {
    if (!batch?.id || !tenant) return;
    if (!["queued", "running"].includes(batch.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const updated = await getDocumentBatch(batch.id);
        setPartial({ batch: updated });
      } catch {
        toast.error("Не удалось обновить batch статус.");
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [batch?.id, batch?.status, setPartial, tenant]);

  return {
    tenant,
    companies,
    sites,
    layoutPresets,
    brandingProfileScope
  };
};
