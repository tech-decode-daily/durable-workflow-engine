import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
class Resize {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = Resize;
window.scrollTo = () => {};
