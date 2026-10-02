import { apiClient } from "./client";
import type { AnalysisRequest, AnalysisResponse } from "../types";

export const analysisApi = {
  analyze: async (payload: AnalysisRequest): Promise<AnalysisResponse> => {
    const { data } = await apiClient.post<AnalysisResponse>("/analysis/multi-document", payload);
    return data;
  },
};
