import { get, post } from "./fetch";
import type { AuthUser, LoginData, LoginParams } from "./types";

export const authApi = {
  login: (params: LoginParams): Promise<LoginData> => {
    return post<LoginData>("/auth/login", params);
  },
  me: (): Promise<AuthUser> => {
    return get<AuthUser>("/auth/me");
  },
};
