import { apiClient } from "./client";
import type {
  ChunkListResponse,
  CloudProvider,
  Document,
  DocumentListResponse,
  DocumentStatus,
  ProcessingStatus,
  ProcessResponse,
  SummarizeResponse,
  TableListResponse,
} from "../types";

export interface ListDocumentsParams {
  provider?: CloudProvider;
  processingStatus?: ProcessingStatus;
  limit?: number;
  offset?: number;
}

export const documentsApi = {
  list: async (params: ListDocumentsParams = {}): Promise<DocumentListResponse> => {
    const { data } = await apiClient.get<DocumentListResponse>("/documents", {
      params: {
        provider: params.provider,
        processing_status: params.processingStatus,
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      },
    });
    return data;
  },

  get: async (documentId: string): Promise<Document> => {
    const { data } = await apiClient.get<Document>(`/documents/${documentId}`);
    return data;
  },

  process: async (documentId: string): Promise<ProcessResponse> => {
    const { data } = await apiClient.post<ProcessResponse>(`/documents/${documentId}/process`);
    return data;
  },

  status: async (documentId: string): Promise<DocumentStatus> => {
    const { data } = await apiClient.get<DocumentStatus>(`/documents/${documentId}/status`);
    return data;
  },

  chunks: async (documentId: string, limit = 50): Promise<ChunkListResponse> => {
    const { data } = await apiClient.get<ChunkListResponse>(`/documents/${documentId}/chunks`, {
      params: { limit },
    });
    return data;
  },

  tables: async (documentId: string): Promise<TableListResponse> => {
    const { data } = await apiClient.get<TableListResponse>(`/documents/${documentId}/tables`);
    return data;
  },

  summarize: async (documentId: string): Promise<SummarizeResponse> => {
    const { data } = await apiClient.post<SummarizeResponse>(`/documents/${documentId}/summarize`);
    return data;
  },
};
