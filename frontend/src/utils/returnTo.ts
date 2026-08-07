import {
  sessionStorageGetItem,
  sessionStorageRemoveItem,
  sessionStorageSetItem,
} from "@/utils/browserStorage";

const RETURN_TO_KEY = "prt-return-to";

export const setReturnTo = (path: string) => {
  sessionStorageSetItem(RETURN_TO_KEY, path);
};

export const consumeReturnTo = (): string | null => {
  const value = sessionStorageGetItem(RETURN_TO_KEY);
  if (value) {
    sessionStorageRemoveItem(RETURN_TO_KEY);
  }
  return value;
};
