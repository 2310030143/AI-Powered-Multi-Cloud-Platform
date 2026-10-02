import { apiClient } from "./client";
import type { ReportGenerateRequest, ReportResponse } from "../types";

export const reportsApi = {
  generate: async (payload: ReportGenerateRequest): Promise<ReportResponse> => {
    const { data } = await apiClient.post<ReportResponse>("/reports/generate", payload);
    return data;
  },
};
