import {
  browserSupportsWebAuthn,
  browserSupportsWebAuthnAutofill,
  startAuthentication,
  startRegistration,
  WebAuthnError,
} from "@simplewebauthn/browser";

import { api } from "@/api/client";
import type { Me, Passkey } from "@/api/types";

import { describeDevice } from "./device";

/** Passkeys need WebAuthn and a secure origin (HTTPS, or localhost). */
export function passkeysSupported(): boolean {
  return window.isSecureContext && browserSupportsWebAuthn();
}

export async function passkeyAutofillSupported(): Promise<boolean> {
  return passkeysSupported() && (await browserSupportsWebAuthnAutofill());
}

/**
 * Sign in with a passkey. With `autofill`, the request waits quietly and the
 * browser offers saved passkeys in the username field's autofill.
 */
export async function signInWithPasskey(autofill = false): Promise<Me> {
  const { challenge_id, options } = await api.passkeys.loginOptions();
  const credential = await startAuthentication({
    optionsJSON: options,
    useBrowserAutofill: autofill,
  });
  return api.passkeys.login(challenge_id, credential);
}

/** Create a passkey on this device for the signed-in account. */
export async function addPasskey(): Promise<Passkey> {
  const { challenge_id, options } = await api.passkeys.registerOptions();
  const credential = await startRegistration({ optionsJSON: options });
  return api.passkeys.register(challenge_id, credential, describeDevice(navigator.userAgent));
}

/** True when the user just closed or cancelled the passkey prompt. */
export function isCancelled(error: unknown): boolean {
  const cause = error instanceof WebAuthnError ? error.cause : error;
  const name = cause instanceof Error ? cause.name : undefined;
  return name === "NotAllowedError" || name === "AbortError";
}

/** Plain-language message for a failed passkey action. */
export function passkeyErrorMessage(error: unknown): string {
  if (
    error instanceof WebAuthnError &&
    error.code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED"
  ) {
    return "This device already has a passkey for your account.";
  }
  return error instanceof Error ? error.message : "Something went wrong with the passkey.";
}
