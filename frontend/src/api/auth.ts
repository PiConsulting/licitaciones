import apiClient from "./client";
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
} from "../types/auth";

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>("/auth/login", payload);
  return response.data;
}

export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  const response = await apiClient.post<RegisterResponse>("/auth/register", payload);
  return response.data;
}

export function logout(): void {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_name");
  localStorage.removeItem("user_email");
}
