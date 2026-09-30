export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  name: string;
  email: string;
  role: string;
  business_unit: string | null;
}

export interface CurrentUserResponse {
  id: string;
  name: string;
  email: string;
  role: string;
  business_unit: string | null;
  is_active: boolean;
}

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
}

export interface RegisterResponse {
  id: string;
  email: string;
  name: string;
}
