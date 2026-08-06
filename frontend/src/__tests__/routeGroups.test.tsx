import type { ReactElement, ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { buildProtectedRouteGroups } from "@/router/routeGroups";

const collectPaths = (node: ReactNode): string[] => {
  if (node == null || typeof node === "boolean") {
    return [];
  }
  if (Array.isArray(node)) {
    return node.flatMap(collectPaths);
  }
  if (typeof node === "string" || typeof node === "number") {
    return [];
  }

  const element = node as ReactElement<{ path?: string; children?: ReactNode }>;
  const ownPath = element.props.path ? [element.props.path] : [];
  return [...ownPath, ...collectPaths(element.props.children)];
};

describe("buildProtectedRouteGroups", () => {
  it("preserves critical deep-link routes after route-group extraction", () => {
    const paths = collectPaths(buildProtectedRouteGroups());

    expect(paths).toEqual(
      expect.arrayContaining([
        "/dashboard",
        "/workspace/attention",
        "/documents/wizard",
        "/findings",
        "/corrective-actions",
        "/audit-prep",
        "/client-portal/requests",
        "/pipelines/runs/:id",
        "/generate-pack/:presetId",
      ]),
    );
  });

  it("keeps a single guarded route entry per permission cluster", () => {
    const groups = buildProtectedRouteGroups();

    // Each group is rendered with key={permission}; one guarded entry per
    // permission cluster means those keys must be unique (no duplicated guard
    // for the same permission). Asserting uniqueness is faithful to that intent
    // and does not break when new distinct clusters are added.
    const keys = groups.map((group) => group.key);

    expect(keys).not.toContain(null);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
