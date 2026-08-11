import { z } from "zod";

export const loginSchema = z.object({
  tenant: z.string().trim().min(1, "Укажите tenant"),
  email: z.string().email(),
  password: z.string().min(8),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
