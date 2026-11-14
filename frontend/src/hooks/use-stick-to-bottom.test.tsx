import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useStickToBottom } from "./use-stick-to-bottom";

let follow = () => {};

function Chat({ text }: { text: string }) {
  const scroller = useStickToBottom<HTMLDivElement>(text);
  follow = scroller.follow;
  return (
    <div data-testid="chat" ref={scroller.ref} onScroll={scroller.onScroll}>
      {text}
    </div>
  );
}

/** jsdom has no layout, so give the element a fixed size and a growing content height. */
function sized(el: HTMLElement, height: { current: number }) {
  Object.defineProperty(el, "clientHeight", { configurable: true, value: 200 });
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => height.current });
}

describe("chat auto-scroll", () => {
  it("follows new text, pauses while reading earlier messages, and resumes", () => {
    const height = { current: 1000 };
    const { rerender } = render(<Chat text="a" />);
    const chat = screen.getByTestId("chat");
    sized(chat, height);

    rerender(<Chat text="ab" />);
    expect(chat.scrollTop).toBe(1000); // following the reply as it streams

    chat.scrollTop = 100; // the reader scrolls up
    fireEvent.scroll(chat);
    height.current = 1400;
    rerender(<Chat text="abc" />);
    expect(chat.scrollTop).toBe(100); // left where they are

    chat.scrollTop = 1180; // back near the bottom
    fireEvent.scroll(chat);
    height.current = 1600;
    rerender(<Chat text="abcd" />);
    expect(chat.scrollTop).toBe(1600);

    chat.scrollTop = 0;
    fireEvent.scroll(chat);
    act(() => follow()); // sending a prompt jumps to the end
    expect(chat.scrollTop).toBe(1600);
  });
});
