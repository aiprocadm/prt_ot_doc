import { z } from "zod";

export const personSchema = z.object({
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  middle_name: z.string().optional(),
  position: z.string().optional(),
  email: z.string().email().optional(),
  phone: z.string().optional(),
  status: z.enum(["active", "inactive", "dismissed"])
});

export type PersonFormValues = z.infer<typeof personSchema>;
