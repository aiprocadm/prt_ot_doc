export type MobileIssueStep = "worker" | "items" | "review";

export type CartLine = {
  item_id: string;
  item_name: string;
  quantity: number;
  on_hand: number | null; // null = stock unknown (warehouse flag off / no data)
};

export type IssueResultLine = {
  item_id: string;
  item_name: string;
  quantity: number;
  status: "ok" | "error";
  error?: string;
};
