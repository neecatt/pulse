import { useEffect, useState } from "react";

/** Below the sticky header: a heading counts as current once it scrolls past this. */
const OFFSET = 96;

/** The id of the section being read: the last heading scrolled past the top. */
export function useActiveSection(ids: string[]): string | undefined {
  const [active, setActive] = useState<string>();

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      let current = ids[0];
      for (const id of ids) {
        const top = document.getElementById(id)?.getBoundingClientRect().top;
        if (top === undefined || top > OFFSET) break;
        current = id;
      }
      // At the very bottom the last sections can't reach the top; show the last one.
      const atEnd = window.innerHeight + window.scrollY >= document.body.scrollHeight - 2;
      setActive(atEnd ? ids.at(-1) : current);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [ids]);

  return active;
}
