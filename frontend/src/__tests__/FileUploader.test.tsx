import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileUploader } from "@/features/files/FileUploader";

const createUploadSessionMock = vi.fn();
const finalizeUploadMock = vi.fn();
const getFileMock = vi.fn();
const putMock = vi.fn();

vi.mock("@/api/files", () => ({
  createUploadSession: (...args: unknown[]) => createUploadSessionMock(...args),
  finalizeUpload: (...args: unknown[]) => finalizeUploadMock(...args),
  getFile: (...args: unknown[]) => getFileMock(...args)
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    put: (...args: unknown[]) => putMock(...args)
  }
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn()
  }
}));

describe("FileUploader", () => {
  beforeEach(() => {
    createUploadSessionMock.mockReset();
    finalizeUploadMock.mockReset();
    getFileMock.mockReset();
    putMock.mockReset();
  });

  it("uploads file and shows ready progress", async () => {
    createUploadSessionMock.mockResolvedValue({ file_id: "f-1", signed_put_url: "https://upload" });
    putMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "ready" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const input = screen.getByLabelText("Описание файла");
    await user.type(input, "Первичная загрузка");

    const file = new File(["123"], "test.pdf", { type: "application/pdf" });
    const uploaderInput = screen.getByText(/Перетащите файлы сюда/).parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, file);

    expect(await screen.findByText("test.pdf")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/100%/)).toBeInTheDocument());
    expect(createUploadSessionMock).toHaveBeenCalled();
  });

  it("disables new drops while upload is in progress", async () => {
    let uploadResolver: (() => void) | undefined;
    createUploadSessionMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          uploadResolver = () => resolve({ file_id: "f-3", signed_put_url: "https://upload" });
        })
    );
    putMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "ready" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const file = new File(["123"], "pending.pdf", { type: "application/pdf" });
    const uploaderInput = screen.getByText(/Перетащите файлы сюда/).parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, file);

    const uploadingHint = await screen.findByText("Загрузка в процессе. Дождитесь завершения.");
    expect(uploadingHint).toBeInTheDocument();
    expect(uploadingHint.parentElement).toHaveAttribute("aria-disabled", "true");

    uploadResolver?.();
    await waitFor(() => expect(screen.getByText(/100%/)).toBeInTheDocument());
  });

  it("shows file processing error", async () => {
    createUploadSessionMock.mockResolvedValue({ file_id: "f-2", signed_put_url: "https://upload" });
    putMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "infected" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const file = new File(["123"], "bad.pdf", { type: "application/pdf" });
    const uploaderInput = screen.getByText(/Перетащите файлы сюда/).parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, file);

    expect(await screen.findByText(/не прошёл AV-проверку/)).toBeInTheDocument();
  });
});
