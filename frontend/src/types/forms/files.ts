import { z } from "zod";

export const uploadFileSchema = z.object({
  file: z.instanceof(File),
  description: z.string().optional(),
  tags: z.array(z.string()).optional(),
});

export type UploadFileFormValues = z.infer<typeof uploadFileSchema>;
