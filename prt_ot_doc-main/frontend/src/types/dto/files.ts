import type { BaseEntityDto } from "./common";

export interface FileDto extends BaseEntityDto {
  name: string;
  mime_type: string;
  size: number;
  url: string;
  description?: string;
  tags?: string[];
  linked_object?: {
    id: string;
    type: string;
  };
}

export interface UploadFileDto {
  file: File;
  description?: string;
  tags?: string[];
}
