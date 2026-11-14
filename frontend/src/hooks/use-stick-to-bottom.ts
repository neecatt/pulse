import { useCallback, useLayoutEffect, useRef } from "react";

/** How close to the bottom (px) still counts as "following along". */
const SLACK = 80;

/**
 * Keep a scrolling element at its bottom as content arrives, like a chat: it
 * follows new text unless the reader scrolled up, and follows again once they
 * scroll back down. ``follow()`` pins it again, e.g. after sending a message.
 */
export function useStickToBottom<T extends HTMLElement>(content: unknown) {
  const ref = useRef<T>(null);
  const pinned = useRef(true);

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < SLACK;
  }, []);

  const follow = useCallback(() => {
    pinned.current = true;
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [content]);

  return { ref, onScroll, follow };
}
