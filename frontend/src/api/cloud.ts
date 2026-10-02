import { apiClient } from "./client";
import type {
  ConnectionStatus,
  GoogleConnectResponse,
  S3ConnectRequest,
  S3ConnectResponse,
} from "../types";

export const cloudApi = {
  googleStatus: async (): Promise<ConnectionStatus> => {
    const { data } = await apiClient.get<ConnectionStatus>("/cloud/google/status");
    return data;
  },

  googleConnect: async (): Promise<GoogleConnectResponse> => {
    const { data } = await apiClient.get<GoogleConnectResponse>("/cloud/google/connect");
    return data;
  },

  googleDisconnect: async (): Promise<ConnectionStatus> => {
    const { data } = await apiClient.delete<ConnectionStatus>("/cloud/google/disconnect");
    return data;
  },

  s3Status: async (): Promise<ConnectionStatus> => {
    const { data } = await apiClient.get<ConnectionStatus>("/cloud/s3/status");
    return data;
  },

  s3Connect: async (payload: S3ConnectRequest): Promise<S3ConnectResponse> => {
    const { data } = await apiClient.post<S3ConnectResponse>("/cloud/s3/connect", payload);
    return data;
  },

  s3Disconnect: async (): Promise<ConnectionStatus> => {
    const { data } = await apiClient.delete<ConnectionStatus>("/cloud/s3/disconnect");
    return data;
  },
};
