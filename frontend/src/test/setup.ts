import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest runs with globals: false, so React Testing Library's automatic
// cleanup must be registered explicitly (otherwise renders accumulate
// between tests and queries find duplicate elements).
afterEach(() => {
  cleanup();
});

// jsdom does not implement scrollIntoView; stub it for components that rely on it
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => undefined;
}
