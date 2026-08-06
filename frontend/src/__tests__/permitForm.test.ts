import { describe, expect, it } from "vitest";
import { permitFormSchema } from "@/types/forms/permits";

describe("permitFormSchema", () => {
  it("rejects missing person and type", () => {
    const result = permitFormSchema.safeParse({
      person_id: "",
      permit_type: "",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid permit form", () => {
    const result = permitFormSchema.safeParse({
      person_id: "p1",
      permit_type: "Работа на высоте",
      issued_at: "2026-01-12",
      valid_until: "2027-01-12",
    });
    expect(result.success).toBe(true);
  });
});
