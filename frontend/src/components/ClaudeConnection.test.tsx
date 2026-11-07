import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";

import { ClaudeConnection } from "./ClaudeConnection";

const mock = vi.hoisted(() => ({
  state: {
    connection_id: "one",
    phase: "disconnected",
    running: false,
    work_dir: "",
    session_id: null,
    login_url: null,
    remote_url: null as string | null,
    setup_text: "",
    error: null,
  },
  confirm: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}));
vi.mock("@/hooks/use-confirm", () => ({
  useConfirm: () => ({ ask: mock.confirm, dialog: null }),
}));
vi.mock("@/hooks/use-assistant", () => ({
  useClaude: () => ({ data: mock.state }),
  useClaudeThreads: () => ({
    data: {
      data: [
        {
          id: "11111111-1111-4111-8111-111111111111",
          title: "Saved Claude chat",
          work_dir: "/scratch/project",
        },
      ],
    },
    refetch: vi.fn(),
  }),
  useAssistantAction: (_account: number, action: (value: unknown) => Promise<unknown>) => ({
    mutate: (value: unknown, options?: { onSuccess?: () => void }) => {
      void action(value).then(() => options?.onSuccess?.());
    },
    isPending: false,
  }),
}));

describe("native Claude connection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mock.confirm.mockReset();
    Object.assign(mock.state, {
      phase: "disconnected",
      running: false,
      remote_url: null,
      setup_text: "",
    });
  });

  it("asks before resuming a saved conversation on the cluster", async () => {
    const start = vi
      .spyOn(api.claude, "start")
      .mockResolvedValue({ ...mock.state, phase: "starting" });
    render(<ClaudeConnection account={2} verified />);
    fireEvent.click(screen.getByText("Continue in Claude"));
    expect(start).not.toHaveBeenCalled();
    const options = mock.confirm.mock.calls[0]?.[0] as { onConfirm: () => void };
    options.onConfirm();
    await waitFor(() =>
      expect(start).toHaveBeenCalledWith(
        2,
        "/scratch/project",
        "11111111-1111-4111-8111-111111111111",
      ),
    );
  });

  it("opens the official Claude session when ready", () => {
    Object.assign(mock.state, {
      phase: "ready",
      running: true,
      remote_url: "https://claude.ai/code/session_test",
    });
    render(<ClaudeConnection account={2} verified />);
    expect(screen.getByRole("link", { name: /Open in Claude/ })).toHaveAttribute(
      "href",
      "https://claude.ai/code/session_test",
    );
  });

  it("never answers native trust prompts automatically", async () => {
    Object.assign(mock.state, {
      phase: "starting",
      running: true,
      setup_text: "Trust this project?",
    });
    const setup = vi.spyOn(api.claude, "setup").mockResolvedValue();
    render(<ClaudeConnection account={2} verified />);
    expect(setup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(setup).toHaveBeenCalledWith(2, "yes", undefined));
  });
});
