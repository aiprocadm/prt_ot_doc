import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FileUploader } from "@/features/files/FileUploader";
import { toast } from "sonner";

const createUploadSessionMock = vi.fn();
const finalizeUploadMock = vi.fn();
const getFileMock = vi.fn();
const uploadToSignedUrlMock = vi.fn();

vi.mock("@/api/files", () => ({
  createUploadSession: (...args: unknown[]) => createUploadSessionMock(...args),
  finalizeUpload: (...args: unknown[]) => finalizeUploadMock(...args),
  getFile: (...args: unknown[]) => getFileMock(...args),
  uploadToSignedUrl: (...args: unknown[]) => uploadToSignedUrlMock(...args),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

describe("FileUploader", () => {
  beforeEach(() => {
    createUploadSessionMock.mockReset();
    finalizeUploadMock.mockReset();
    getFileMock.mockReset();
    uploadToSignedUrlMock.mockReset();
  });

  it("uploads file and shows ready progress", async () => {
    createUploadSessionMock.mockResolvedValue({
      file_id: "f-1",
      signed_put_url: "https://upload",
    });
    uploadToSignedUrlMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "ready" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const input = screen.getByLabelText("Описание файла");
    await user.type(input, "Первичная загрузка");

    const file = new File(["123"], "test.pdf", { type: "application/pdf" });
    const uploaderInput = screen
      .getByText(/Перетащите файлы сюда/)
      .parentElement?.querySelector("input[type='file']") as HTMLInputElement;

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
          uploadResolver = () =>
            resolve({ file_id: "f-3", signed_put_url: "https://upload" });
        }),
    );
    uploadToSignedUrlMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "ready" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const file = new File(["123"], "pending.pdf", { type: "application/pdf" });
    const uploaderInput = screen
      .getByText(/Перетащите файлы сюда/)
      .parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, file);

    const uploadingHint = await screen.findByText(
      "Загрузка в процессе. Дождитесь завершения.",
    );
    expect(uploadingHint).toBeInTheDocument();
    expect(uploadingHint.parentElement).toHaveAttribute(
      "aria-disabled",
      "true",
    );

    uploadResolver?.();
    await waitFor(() => expect(screen.getByText(/100%/)).toBeInTheDocument());
  });

  it("shows file processing error", async () => {
    createUploadSessionMock.mockResolvedValue({
      file_id: "f-2",
      signed_put_url: "https://upload",
    });
    uploadToSignedUrlMock.mockResolvedValue({});
    finalizeUploadMock.mockResolvedValue({});
    getFileMock.mockResolvedValue({ status: "infected" });

    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const file = new File(["123"], "bad.pdf", { type: "application/pdf" });
    const uploaderInput = screen
      .getByText(/Перетащите файлы сюда/)
      .parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, file);

    expect(
      await screen.findByText(/не прошёл AV-проверку/),
    ).toBeInTheDocument();
  });

  it("shows explicit error message for unsupported files", async () => {
    const user = userEvent.setup();
    render(<FileUploader pollAttempts={1} pollIntervalMs={0} />);

    const invalid = new File(["123"], "malware.exe", {
      type: "application/octet-stream",
    });
    const uploaderInput = screen
      .getByText(/Перетащите файлы сюда/)
      .parentElement?.querySelector("input[type='file']") as HTMLInputElement;

    await user.upload(uploaderInput, invalid);

    expect(toast.error).toHaveBeenCalled();
    const calls = vi.mocked(toast.error).mock.calls.flat().map(String);
    expect(
      calls.some(
        (message) =>
          message.includes("Файлы отклонены:") ||
          message.includes("Не удалось загрузить выбранные файлы"),
      ),
    ).toBe(true);
  });
});
