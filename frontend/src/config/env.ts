/**
 * The only module that reads build-time environment variables (see
 * frontend/.env.example). Vite exposes only variables prefixed with VITE_,
 * and everything here ends up in the public bundle: never put secrets in it.
 */

/** Origin of the Pulse API. Empty means same origin as the web app. */
export const API_URL: string = import.meta.env["VITE_API_URL"] ?? "";

/** Origin agents on clusters must reach: the API's, or this page's. */
export const PUBLIC_ORIGIN: string = API_URL || window.location.origin;
