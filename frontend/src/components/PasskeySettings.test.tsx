import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { startAuthentication } from "@simplewebauthn/browser";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/api/client";
import { addPasskey } from "@/lib/passkeys";
import { PasskeySettings } from "./PasskeySettings";

const { existing } = vi.hoisted(() => ({
  existing: {
    passkeys: [] as { id: number; name: string; last_used_at: null }[],
    hasPassword: true,
  },
}));

vi.mock("@/api/queries", () => ({
  queryKeys: { passkeys: ["passkeys"], assistantAccess: ["assistants", "access"] },
  useMe: () => ({ data: { has_password: existing.hasPassword } }),
  usePasskeys: () => ({ data: existing.passkeys }),
}));
vi.mock("@simplewebauthn/browser", () => ({ startAuthentication: vi.fn() }));
vi.mock("@/lib/passkeys", () => ({
  addPasskey: vi.fn(),
  isCancelled: () => false,
  passkeysSupported: () => true,
  passkeyErrorMessage: (error: Error) => error.message,
}));

function settings() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PasskeySettings />
    </QueryClientProvider>,
  );
}

async function confirmPassword() {
  fireEvent.change(await screen.findByLabelText("Current password"), {
    target: { value: "my password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm password" }));
}

describe("passkey change confirmation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(addPasskey).mockReset();
    existing.passkeys = [];
    existing.hasPassword = true;
    HTMLDialogElement.prototype.showModal = function () {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function () {
      this.open = false;
      fireEvent(this, new Event("close"));
    };
  });

  it("asks in place and retries adding only after password confirmation succeeds", async () => {
    vi.mocked(addPasskey)
      .mockRejectedValueOnce(new ApiError(403, "Confirm your password or passkey to continue."))
      .mockResolvedValueOnce({ id: 2, name: "Phone", created_at: "", last_used_at: null });
    const reauth = vi
      .spyOn(api.auth, "reauthenticate")
      .mockRejectedValueOnce(new ApiError(403, "Wrong password."))
      .mockResolvedValueOnce();
    settings();
    fireEvent.click(screen.getByRole("button", { name: "Add a passkey" }));
    await screen.findByText("Confirm it’s you before changing your passkeys.");
    expect(addPasskey).toHaveBeenCalledTimes(1);
    // With no existing passkey, confirmation must use the password.
    expect(screen.queryByRole("button", { name: "Use passkey" })).not.toBeInTheDocument();
    await confirmPassword();
    await screen.findByText("Wrong password.");
    expect(addPasskey).toHaveBeenCalledTimes(1);
    await confirmPassword();
    await waitFor(() => expect(addPasskey).toHaveBeenCalledTimes(2));
    expect(reauth).toHaveBeenLastCalledWith("my password");
    await waitFor(() =>
      expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument(),
    );
  });

  it("retries a confirmed removal after reauthentication", async () => {
    existing.passkeys = [{ id: 7, name: "Old phone", last_used_at: null }];
    const remove = vi
      .spyOn(api.passkeys, "remove")
      .mockRejectedValueOnce(new ApiError(403, "Confirm your password or passkey to continue."))
      .mockResolvedValueOnce();
    vi.spyOn(api.auth, "reauthenticate").mockResolvedValue();
    settings();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove passkey" }));
    await screen.findByText("Confirm it’s you before changing your passkeys.");
    expect(remove).toHaveBeenCalledTimes(1);
    await confirmPassword();
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(2));
    expect(remove).toHaveBeenLastCalledWith(7);
    await waitFor(() =>
      expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument(),
    );
  });

  it("confirms a passwordless account with an existing passkey before adding another", async () => {
    existing.hasPassword = false;
    existing.passkeys = [{ id: 7, name: "Phone", last_used_at: null }];
    vi.mocked(addPasskey)
      .mockRejectedValueOnce(new ApiError(403, "Confirm your password or passkey to continue."))
      .mockResolvedValueOnce({ id: 8, name: "Laptop", created_at: "", last_used_at: null });
    const options = { challenge: "challenge", rpId: "test" };
    const credential = {
      id: "credential",
      rawId: "credential",
      type: "public-key" as const,
      response: { authenticatorData: "", clientDataJSON: "", signature: "" },
      clientExtensionResults: {},
    };
    vi.spyOn(api.passkeys, "reauthOptions").mockResolvedValue({
      challenge_id: "confirmation",
      options,
    });
    vi.mocked(startAuthentication).mockResolvedValue(credential);
    const verify = vi.spyOn(api.passkeys, "reauthenticate").mockResolvedValue();
    settings();
    fireEvent.click(screen.getByRole("button", { name: "Add a passkey" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use passkey" }));
    expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
    await waitFor(() => expect(addPasskey).toHaveBeenCalledTimes(2));
    expect(startAuthentication).toHaveBeenCalledWith({ optionsJSON: options });
    expect(verify).toHaveBeenCalledWith("confirmation", credential);
  });
});
