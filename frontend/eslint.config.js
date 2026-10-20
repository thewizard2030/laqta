import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

/**
 * ESLint flat configuration.
 *
 * The rules are deliberately focused on correctness (React hooks, floating
 * promises, accidental globals) rather than style — Prettier owns formatting.
 */
export default tseslint.config(
  {
    ignores: ["dist", "node_modules", "coverage"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // The React Compiler rules target compiler-compatible code. Laqta does
      // not use the compiler, and the flagged patterns are intentional here:
      // data is fetched in effects, and the job panel renders a live elapsed
      // timer. They stay enabled as warnings so the trade-off is visible.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn",
      // TypeScript already checks the types; these are the runtime hazards
      // that survive type checking.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["error", "smart"],
      "prefer-const": "error",
      "no-var": "error",
    },
  },
  {
    // Tests may use loose typing and console output.
    files: ["src/tests/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "no-console": "off",
    },
  },
  {
    // Config files are plain JS.
    files: ["*.js", "*.cjs"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  // Prettier runs last and disables every formatting rule.
  prettier,
);
