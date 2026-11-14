import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AssistantLive } from "@/api/types";
import { api } from "@/api/client";
import { AssistantChat } from "./AssistantChat";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}));
vi.mock("@/hooks/use-assistant", () => ({
  useAssistantHistory: () => ({
    data: {
      thread: { title: "Existing training", work_dir: "/scratch/project" },
      messages: [{ id: "one", role: "assistant", kind: "agentMessage", text: "Saved answer" }],
    },
    isPending: false,
  }),
  useAssistantAction: (_account: number, action: (value: unknown) => Promise<unknown>) => ({
    mutate: (value: unknown, options?: { onSuccess?: () => void }) => {
      void action(value).then(() => options?.onSuccess?.());
    },
    isPending: false,
  }),
}));
const state: AssistantLive = {
  connection: { connected: true, signed_in: true, email: null },
  messages: {},
  active: {},
  opened: [],
  approvals: [],
  error: null,
  revision: 0,
  partial: false,
};

describe("cluster conversation UI", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("shows existing history and resumes only when the user asks", async () => {
    const resume = vi.spyOn(api.assistants, "resume").mockResolvedValue({
      id: "chat",
      title: "Existing",
      work_dir: "/scratch/project",
      updated_at: 0,
    });
    render(<AssistantChat account={2} provider="codex" id="chat" live={state} verified />);
    expect(screen.getByText("Saved answer")).toBeInTheDocument();
    expect(resume).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Continue this conversation"));
    await waitFor(() => expect(resume).toHaveBeenCalledWith(2, "codex", "chat"));
  });
  it("shows a pending command and never approves it without a click", async () => {
    const decide = vi.spyOn(api.assistants, "decide").mockResolvedValue();
    render(
      <AssistantChat
        account={2}
        provider="claude"
        id="chat"
        verified
        live={{
          ...state,
          opened: ["chat"],
          active: { chat: "turn" },
          approvals: [
            {
              id: "request",
              thread_id: "chat",
              kind: "command",
              title: "Run this command?",
              detail: "sbatch train.sh",
              questions: [],
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("sbatch train.sh")).toBeInTheDocument();
    expect(screen.getByText("Claude")).toBeInTheDocument(); // the saved answer's author
    expect(decide).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Approve once"));
    await waitFor(() => expect(decide).toHaveBeenCalledWith(2, "claude", "request", "accept", {}));
  });
});
