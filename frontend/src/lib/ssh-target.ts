export interface SshTarget {
  username: string;
  host: string;
  port: number;
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
  "-J",
  "-L",
  "-m",
  "-O",
  "-o",
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
 * `ssh -p 2222 jdoe@host`, `ssh -l jdoe host` or `ssh://jdoe@host:2222`.
 */
export function parseSshTarget(input: string): SshTarget | null {
  const tokens = input.trim().split(/\s+/).filter(Boolean);
  if (tokens[0] === "ssh") tokens.shift();

  let username: string | undefined;
  let port = 22;
  let destination: string | undefined;
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i] ?? "";
    if (token === "-p") port = Number(tokens[++i]);
    else if (token === "-l") username = tokens[++i];
    else if (OPTIONS_WITH_VALUE.has(token)) i++;
    else if (!token.startsWith("-") && destination === undefined) destination = token;
  }
  if (!destination) return null;

  let rest = destination.replace(/^ssh:\/\//, "");
  const at = rest.lastIndexOf("@");
  if (at >= 0) {
    username = rest.slice(0, at);
    rest = rest.slice(at + 1);
  }
  const match = /^([^:]+)(?::(\d+))?$/.exec(rest);
  const host = match?.[1]?.toLowerCase();
  if (match?.[2]) port = Number(match[2]);

  if (username === undefined || !USERNAME.test(username)) return null;
  if (host === undefined || !HOSTNAME.test(host)) return null;
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  return { username, host, port };
}
