import apiClient from "./client";
import { clearSession } from "../auth/session";
import type {
  CurrentUserResponse,
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

export async function fetchCurrentUser(): Promise<CurrentUserResponse> {
  const response = await apiClient.get<CurrentUserResponse>("/auth/me");
  return response.data;
}

export function logout(): void {
  clearSession();
}
