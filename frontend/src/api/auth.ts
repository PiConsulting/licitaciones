import apiClient from "./client";
import type { LoginRequest, LoginResponse } from "../types/auth";

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", payload);
  return response.data;
}

export function logout(): void {
  localStorage.removeItem("access_token");
}
