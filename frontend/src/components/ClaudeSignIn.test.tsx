import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";

import { ClaudeSignIn } from "./ClaudeSignIn";

const mock = vi.hoisted(() => ({
  state: {
    connection_id: "one",
    phase: "disconnected",
    running: false,
    login_url: null as string | null,
    setup_text: "",
    error: null,
  },
  confirm: vi.fn(),
}));
vi.mock("@/hooks/use-confirm", () => ({
  useConfirm: () => ({ ask: mock.confirm, dialog: null }),
}));
vi.mock("@/hooks/use-assistant", () => ({
  useClaude: () => ({ data: mock.state }),
  useAssistantAction: (_account: number, action: (value: unknown) => Promise<unknown>) => ({
    mutate: (value: unknown, options?: { onSuccess?: () => void }) => {
      void action(value).then(() => options?.onSuccess?.());
    },
    isPending: false,
  }),
}));

describe("Claude sign-in on the cluster", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mock.confirm.mockReset();
    Object.assign(mock.state, {
      phase: "disconnected",
      running: false,
      login_url: null,
      setup_text: "",
    });
  });

  it("asks before running Claude's login command", async () => {
    const login = vi.spyOn(api.claude, "login").mockResolvedValue({
      ...mock.state,
      phase: "sign_in",
    });
    render(<ClaudeSignIn account={2} verified onSignedIn={vi.fn()} />);
    fireEvent.click(screen.getByText("Sign in on cluster"));
    expect(login).not.toHaveBeenCalled();
    const options = mock.confirm.mock.calls[0]?.[0] as { onConfirm: () => void };
    options.onConfirm();
    await waitFor(() => expect(login).toHaveBeenCalledWith(2));
  });

  it("relays Claude's own link and the one-time code", async () => {
    Object.assign(mock.state, {
      phase: "sign_in",
      running: true,
      login_url: "https://claude.ai/oauth/authorize?x=1",
      setup_text: "Paste code here if prompted:",
    });
    const setup = vi.spyOn(api.claude, "setup").mockResolvedValue();
    render(<ClaudeSignIn account={2} verified onSignedIn={vi.fn()} />);
    expect(screen.getByRole("link", { name: /Continue with Claude/ })).toHaveAttribute(
      "href",
      "https://claude.ai/oauth/authorize?x=1",
    );
    fireEvent.change(screen.getByLabelText("Claude sign-in code"), {
      target: { value: "CODE#1" },
    });
    fireEvent.click(screen.getByText("Finish sign-in"));
    await waitFor(() => expect(setup).toHaveBeenCalledWith(2, "code", "CODE#1"));
  });

  it("reconnects once the CLI is signed in", () => {
    Object.assign(mock.state, { phase: "authorized" });
    const onSignedIn = vi.fn();
    render(<ClaudeSignIn account={2} verified onSignedIn={onSignedIn} />);
    fireEvent.click(screen.getByText("Continue"));
    expect(onSignedIn).toHaveBeenCalled();
  });
});
