import { apiClient } from "./client";
import type { SearchRequest, SearchResponse } from "../types";

export const searchApi = {
  search: async (payload: SearchRequest): Promise<SearchResponse> => {
    const { data } = await apiClient.post<SearchResponse>("/search", payload);
    return data;
  },
};
