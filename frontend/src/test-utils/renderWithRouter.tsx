import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

type RenderWithRouterOptions = {
  routerProps?: MemoryRouterProps;
};

export const renderWithRouter = (
  ui: ReactElement,
  options?: RenderWithRouterOptions,
) =>
  render(
    <MemoryRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
      {...options?.routerProps}
    >
      {ui}
    </MemoryRouter>,
  );
