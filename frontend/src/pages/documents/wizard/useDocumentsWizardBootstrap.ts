import { useEffect, useState } from "react";

import { getBrandingProfile, listLayoutPresets, listSites, type LayoutPresetDto, type SiteDto } from "@/api/branding";
import { useDocumentsWizardRuntimePolling } from "./useDocumentsWizardRuntimePolling";
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

  useDocumentsWizardRuntimePolling({
    tenantSlug: tenant?.slug,
    taskId,
    pipelineRun,
    batch,
    onPipelineRun: (nextPipelineRun) => setPartial({ pipelineRun: nextPipelineRun }),
    onBatch: (nextBatch) => setPartial({ batch: nextBatch })
  });

  return {
    tenant,
    companies,
    sites,
    layoutPresets,
    brandingProfileScope
  };
};
