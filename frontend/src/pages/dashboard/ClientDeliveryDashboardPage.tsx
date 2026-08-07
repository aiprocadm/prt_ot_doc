import { DashboardApiPage } from "@/pages/dashboard/DashboardApiPage";

const ClientDeliveryDashboardPage = () => (
  <DashboardApiPage
    title="Дашборд поставки клиенту"
    endpoint="/analytics/dashboard/client-delivery"
  />
);

export default ClientDeliveryDashboardPage;
