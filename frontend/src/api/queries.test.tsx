import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { queryKeys, setSignedIn } from "./queries";
import type { AuthStatus } from "./types";

const me = { id: 1, username: "nicat", is_admin: true, password_from_env: false };

describe("setSignedIn", () => {
  it("updates auth status in place and drops the previous session's data", () => {
    const client = new QueryClient();
    client.setQueryData<AuthStatus>(queryKeys.authStatus, {
      setup_required: false,
      signup_allowed: true,
      user: me,
    });
    client.setQueryData(queryKeys.accounts, [{ id: 7 }]);
    const statusQuery = client.getQueryCache().find({ queryKey: queryKeys.authStatus });

    setSignedIn(client, null);

    // Same query object, so components subscribed to it see the change.
    expect(client.getQueryCache().find({ queryKey: queryKeys.authStatus })).toBe(statusQuery);
    expect(client.getQueryData<AuthStatus>(queryKeys.authStatus)).toEqual({
      setup_required: false,
      signup_allowed: true,
      user: null,
    });
    expect(client.getQueryData(queryKeys.accounts)).toBeUndefined();
  });
});
