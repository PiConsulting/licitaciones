import { useMutation } from "@tanstack/react-query";

import { register as registerApi } from "../api/auth";
import type { RegisterRequest, RegisterResponse } from "../types/auth";

export function useRegister() {
  return useMutation<RegisterResponse, unknown, RegisterRequest>({
    mutationFn: registerApi,
  });
}
