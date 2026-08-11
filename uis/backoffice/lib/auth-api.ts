import { apiRequest } from "./api";

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  role: "admin" | "manager" | "user";
  created_at: string;
}

export interface Profile {
  id: string;
  user_id: string;
  name: string | null;
  phone: string | null;
  address: string | null;
}

export interface AuthMeResponse {
  email: string;
  role: "admin" | "manager" | "user";
  profile: Profile;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function loginRequest(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function registerRequest(
  email: string,
  password: string,
): Promise<User> {
  return apiRequest<User>("/api/users", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchMeRequest(token: string): Promise<AuthMeResponse> {
  return apiRequest<AuthMeResponse>("/api/auth/me", { token });
}
