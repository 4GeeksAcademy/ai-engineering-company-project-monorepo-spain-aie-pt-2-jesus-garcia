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

export async function forgotPasswordRequest(
  email: string,
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPasswordRequest(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function changePasswordRequest(
  currentPassword: string,
  newPassword: string,
  token: string,
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/auth/change-password", {
    method: "POST",
    token,
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}
