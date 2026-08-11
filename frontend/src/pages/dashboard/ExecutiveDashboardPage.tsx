import { DashboardApiPage } from "@/pages/dashboard/DashboardApiPage";

const ExecutiveDashboardPage = () => (
  <DashboardApiPage
    title="Стратегический дашборд"
    endpoint="/analytics/dashboard/executive"
  />
);

export default ExecutiveDashboardPage;
