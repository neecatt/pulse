import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { registerServiceWorker } from "./lib/push";
import { initUiSettings } from "./lib/ui-settings";
import { ApiError } from "./api/client";
import { setSignedIn } from "./api/queries";
import { DEFAULT_STALE_MS } from "./config/constants";
import { routeTree } from "./routeTree.gen";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: DEFAULT_STALE_MS } },
  queryCache: new QueryCache({
    // A 401 anywhere means the session ended (expired, revoked, password
    // changed elsewhere): drop back to the sign-in screen.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) setSignedIn(queryClient, null);
    },
  }),
});

const router = createRouter({
  routeTree,
  context: { queryClient },
  scrollRestoration: true,
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

initUiSettings();

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Missing #root element");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);

registerServiceWorker();
