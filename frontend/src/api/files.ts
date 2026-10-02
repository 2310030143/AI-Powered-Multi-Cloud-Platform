import { apiClient } from "./client";
import type { CloudFile, CloudProvider, Document, ProcessResponse } from "../types";

export interface ListFilesParams {
  provider?: CloudProvider;
  folderId?: string;
  search?: string;
  limit?: number;
}

export interface UploadParams {
  file: File;
  provider: CloudProvider;
  folderId?: string;
}

export const filesApi = {
  list: async (params: ListFilesParams = {}): Promise<CloudFile[]> => {
    const { data } = await apiClient.get<CloudFile[]>("/files", {
      params: {
        provider: params.provider,
        folder_id: params.folderId,
        search: params.search,
        limit: params.limit ?? 100,
      },
    });
    return data;
  },

  upload: async ({ file, provider, folderId }: UploadParams): Promise<Document> => {
    const form = new FormData();
    form.append("file", file);
    form.append("provider", provider);
    if (folderId) form.append("folder_id", folderId);
    const { data } = await apiClient.post<Document>("/files/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  import: async (fileId: string, provider: CloudProvider): Promise<Document> => {
    const { data } = await apiClient.post<Document>(
      `/files/${encodeURIComponent(fileId)}/import`,
      null,
      { params: { provider } }
    );
    return data;
  },

  process: async (fileId: string, provider: CloudProvider): Promise<ProcessResponse> => {
    const { data } = await apiClient.post<ProcessResponse>(
      `/files/${encodeURIComponent(fileId)}/process`,
      null,
      { params: { provider } }
    );
    return data;
  },

  download: async (fileId: string, provider: CloudProvider): Promise<Blob> => {
    const { data } = await apiClient.get<Blob>(
      `/files/${encodeURIComponent(fileId)}/download`,
      { params: { provider }, responseType: "blob" }
    );
    return data;
  },
};
