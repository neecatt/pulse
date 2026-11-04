export interface JumpHost {
  host: string;
  port: number;
  /** Omitted when it's the same as the login username. */
  username?: string;
}

export interface SshTarget {
  username: string;
  host: string;
  port: number;
  /** From `-J host` or `-o ProxyJump=host`, for login nodes behind a jump host. */
  jump?: JumpHost;
}

// ssh options that take a value, so the value isn't mistaken for the destination.
const OPTIONS_WITH_VALUE = new Set([
  "-b",
  "-c",
  "-D",
  "-E",
  "-e",
  "-F",
  "-I",
  "-i",
  "-L",
  "-m",
  "-O",
  "-Q",
  "-R",
  "-S",
  "-W",
  "-w",
]);
const USERNAME = /^[A-Za-z_][A-Za-z0-9_.-]{0,63}$/;
const HOSTNAME =
  /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$/;

/**
 * Parse what people already type to log in: `jdoe@lumi.csc.fi`,
 * `ssh -p 2222 jdoe@host`, `ssh -l jdoe host`, `ssh://jdoe@host:2222`, and with
 * a jump host `ssh -J gateway.example.org jdoe@host`. One jump host only.
 */
export function parseSshTarget(input: string): SshTarget | null {
  const tokens = input.trim().split(/\s+/).filter(Boolean);
  if (tokens[0] === "ssh") tokens.shift();

  let username: string | undefined;
  let port: number | undefined;
  let jumpSpec: string | undefined;
  let destination: string | undefined;
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i] ?? "";
    if (token === "-p") port = Number(tokens[++i]);
    else if (token === "-l") username = tokens[++i];
    else if (token === "-J") jumpSpec = tokens[++i];
    else if (token === "-o") jumpSpec = proxyJumpOption(tokens[++i]) ?? jumpSpec;
    else if (OPTIONS_WITH_VALUE.has(token)) i++;
    else if (!token.startsWith("-") && destination === undefined) destination = token;
  }
  if (!destination) return null;

  const target = parseHostSpec(destination.replace(/^ssh:\/\//, ""));
  if (!target) return null;
  const login = target.username ?? username;
  const loginPort = target.port ?? port ?? 22;
  if (login === undefined || !USERNAME.test(login) || !validPort(loginPort)) return null;

  const result: SshTarget = { username: login, host: target.host, port: loginPort };
  if (jumpSpec !== undefined) {
    const jump = jumpSpec.includes(",") ? null : parseHostSpec(jumpSpec);
    if (!jump) return null;
    const jumpPort = jump.port ?? 22;
    if (!validPort(jumpPort) || (jump.username !== undefined && !USERNAME.test(jump.username))) {
      return null;
    }
    result.jump = { host: jump.host, port: jumpPort };
    if (jump.username !== undefined && jump.username !== login) {
      result.jump.username = jump.username;
    }
  }
  return result;
}

/** `[user@]host[:port]`; null if the host isn't valid. */
function parseHostSpec(spec: string): { host: string; port?: number; username?: string } | null {
  let rest = spec;
  let username: string | undefined;
  const at = rest.lastIndexOf("@");
  if (at >= 0) {
    username = rest.slice(0, at);
    rest = rest.slice(at + 1);
  }
  const match = /^([^:]+)(?::(\d+))?$/.exec(rest);
  const host = match?.[1]?.toLowerCase();
  if (host === undefined || !HOSTNAME.test(host)) return null;
  return {
    host,
    ...(match?.[2] ? { port: Number(match[2]) } : {}),
    ...(username !== undefined ? { username } : {}),
  };
}

/** The value of `-o ProxyJump=...`, or undefined for any other `-o` option. */
function proxyJumpOption(option: string | undefined): string | undefined {
  const match = /^ProxyJump[= ](.+)$/i.exec(option ?? "");
  return match?.[1];
}

function validPort(port: number): boolean {
  return Number.isInteger(port) && port >= 1 && port <= 65535;
}

/** "jdoe on node.org:2200 via bastion.org", for showing what was understood. */
export function describeSshTarget(target: SshTarget): string {
  const host = (h: string, port: number) => (port === 22 ? h : `${h}:${port}`);
  const via = target.jump
    ? ` via ${target.jump.username ? `${target.jump.username}@` : ""}${host(target.jump.host, target.jump.port)}`
    : "";
  return `${target.username} on ${host(target.host, target.port)}${via}`;
}
