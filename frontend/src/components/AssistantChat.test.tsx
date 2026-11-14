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
      messages: [
        {
          id: "one",
          role: "assistant",
          kind: "agentMessage",
          text: "Saved answer with **bold**, [a guide](https://example.org) and [x](javascript:alert(1))",
        },
      ],
    },
    isPending: false,
  }),
  useAssistantModels: () => ({
    data: [
      {
        id: "default",
        name: "Default (recommended)",
        description: "",
        efforts: ["low", "high"],
        default_effort: null,
        is_default: true,
      },
      {
        id: "sonnet",
        name: "Sonnet",
        description: "",
        efforts: ["low", "high"],
        default_effort: null,
        is_default: false,
      },
    ],
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
    render(<AssistantChat account={2} provider="codex" id="chat" live={state} />);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByRole("link", { name: "a guide" })).toHaveAttribute(
      "href",
      "https://example.org",
    );
    expect(screen.queryByRole("link", { name: "x" })).toBeNull(); // never a javascript: link
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

  it("sends the model and thinking level picked under the prompt", async () => {
    localStorage.clear();
    const turn = vi.spyOn(api.assistants, "turn").mockResolvedValue();
    render(
      <AssistantChat
        account={2}
        provider="claude"
        id="chat"
        live={{ ...state, opened: ["chat"] }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "sonnet" } });
    fireEvent.change(screen.getByLabelText("Thinking"), { target: { value: "low" } });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "train" } });
    fireEvent.click(screen.getByText("Send"));
    await waitFor(() =>
      expect(turn).toHaveBeenCalledWith(2, "claude", "chat", "train", {
        model: "sonnet",
        effort: "low",
      }),
    );
    expect(JSON.parse(localStorage.getItem("pulse.assistant-choice.claude") ?? "{}")).toEqual({
      model: "sonnet",
      effort: "low",
    });
  });
});
