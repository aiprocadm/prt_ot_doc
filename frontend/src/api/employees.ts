import { apiClient } from "@/api/client";
import type { EmployeeCardDto } from "@/types/dto/employee";

export const employeesApi = {
  async getCard(personId: string): Promise<EmployeeCardDto> {
    const { data } = await apiClient.get<EmployeeCardDto>(
      `/employees/${encodeURIComponent(personId)}`
    );
    return data;
  }
};
