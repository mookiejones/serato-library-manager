import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["static/**", "node_modules/**"] },
  {
    files: ["src/**/*.ts", "e2e/**/*.ts"],
    extends: [tseslint.configs.base],
    languageOptions: {
      parserOptions: {
        projectService: false,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/ban-ts-comment": ["error", {
        "ts-expect-error": "allow-with-description",
        "ts-ignore": true,
        "ts-nocheck": true,
        "ts-check": false,
      }],
    },
  },
);
