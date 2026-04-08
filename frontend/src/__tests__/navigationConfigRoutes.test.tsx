import type { ReactElement, ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { MAIN_NAV_GROUPS } from "@/router/navigationConfig";
import { buildProtectedRouteGroups } from "@/router/routeGroups";

const collectPaths = (node: ReactNode): string[] => {
  if (node == null || typeof node === "boolean" || typeof node === "string" || typeof node === "number") {
    return [];
  }
  if (Array.isArray(node)) {
    return node.flatMap(collectPaths);
  }
  const element = node as ReactElement<{ path?: string; children?: ReactNode }>;
  const ownPath = element.props.path ? [element.props.path] : [];
  return [...ownPath, ...collectPaths(element.props.children)];
};

describe("navigation config", () => {
  it("keeps all main navigation links routable", () => {
    const protectedPaths = new Set(collectPaths(buildProtectedRouteGroups()));
    const navPaths = MAIN_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.to));

    expect(navPaths.every((path) => protectedPaths.has(path))).toBe(true);
  });
});

