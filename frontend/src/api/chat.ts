import { apiClient } from "./client";
import type { ChatRequest, ChatResponse } from "../types";

export const chatApi = {
  send: async (payload: ChatRequest): Promise<ChatResponse> => {
    const { data } = await apiClient.post<ChatResponse>("/chat", payload);
    return data;
  },
};
