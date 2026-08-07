import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReplaceDiffViewer } from "@/components/wizard/ReplaceDiffViewer";

describe("ReplaceDiffViewer", () => {
  it("renders summary and rows", () => {
    render(
      <ReplaceDiffViewer
        summary={{ matches: 3, pairs: { "ООО->АО": 3 } }}
        items={[
          {
            from: "ООО",
            to: "АО",
            part: "body",
            location: "p1",
            before: "ООО Ромашка",
            after: "АО Ромашка",
            context: "ctx",
            match_count: 3,
          },
        ]}
      />,
    );

    expect(screen.getByText(/совпадений: 3/i)).toBeInTheDocument();
    expect(screen.getByText("ООО")).toBeInTheDocument();
    expect(screen.getByText("АО Ромашка")).toBeInTheDocument();
  });
});
