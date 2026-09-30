import apiClient from "./client";
import type { CreateUserPayload, SystemUser, UpdateUserPayload } from "../types/users";

export async function fetchUsers(): Promise<SystemUser[]> {
  const response = await apiClient.get<SystemUser[]>("/users");
  return response.data;
}

export async function createUser(payload: CreateUserPayload): Promise<SystemUser> {
  const response = await apiClient.post<SystemUser>("/users", payload);
  return response.data;
}

export async function updateUser(userId: string, payload: UpdateUserPayload): Promise<SystemUser> {
  const response = await apiClient.patch<SystemUser>(`/users/${userId}`, payload);
  return response.data;
}
