import AppRouter from "@/router/AppRouter";
import { AppErrorBoundary } from "@/components/common/AppErrorBoundary";

const App = () => (
  <AppErrorBoundary>
    <AppRouter />
  </AppErrorBoundary>
);

export default App;
