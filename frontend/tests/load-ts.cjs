const { readFileSync, existsSync } = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const ts = require("typescript");
const { jsx } = require("react/jsx-runtime");

// Exercise actual TS/TSX modules using the project's existing compiler and React.
// Framework navigation is replaced only at the runtime boundary.
module.exports = function createLoader({ fetch = global.fetch, view, pathname = "/" } = {}) {
  const cache = new Map();
  function load(filename) {
    const resolved = path.resolve(__dirname, filename);
    if (cache.has(resolved)) return cache.get(resolved).exports;
    const module = { exports: {} };
    cache.set(resolved, module);
    const localRequire = createRequire(resolved);
    const source = ts.transpileModule(readFileSync(resolved, "utf8"), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        target: ts.ScriptTarget.ES2022
      }
    }).outputText;
    new Function("require", "module", "exports", "fetch", source)(
      (name) => {
        if (name === "next/link")
          return {
            default: ({ children, ...props }) =>
              jsx("a", { ...props, children })
          };
        if (name === "next/navigation")
          return {
            usePathname: () => pathname,
            notFound: () => {
              throw new Error("NEXT_NOT_FOUND");
            }
          };
        if (name === "react" && view)
          return { ...localRequire(name), useState: () => [view, () => {}] };
        if (name === "./analytics-panel") return { default: () => null };
        if (name.startsWith(".")) {
          const base = path.resolve(path.dirname(resolved), name);
          const target = [base, `${base}.ts`, `${base}.tsx`].find((candidate) =>
            existsSync(candidate)
          );
          return load(target);
        }
        return localRequire(name);
      },
      module,
      module.exports,
      fetch
    );
    return module.exports;
  }
  return load;
};
