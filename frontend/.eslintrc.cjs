module.exports = {
  ignorePatterns: ["dev-dist/**", "dist/**", "coverage/**"],
  env: {
    browser: true,
    es2021: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
    "prettier",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaFeatures: {
      jsx: true,
    },
    ecmaVersion: "latest",
    sourceType: "module",
  },
  plugins: ["react", "@typescript-eslint", "react-hooks", "jsx-a11y"],
  settings: {
    react: {
      version: "detect",
    },
  },
  rules: {
    "react/react-in-jsx-scope": "off",
    "react/prop-types": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
      },
    ],
    "no-restricted-globals": [
      "error",
      {
        name: "fetch",
        message: "Use apiClient from @/api/client to enforce tenant scoping.",
      },
    ],
    "no-restricted-imports": [
      "error",
      {
        paths: [
          {
            name: "axios",
            message: "Use apiClient from @/api/client instead of raw axios.",
          },
        ],
      },
    ],
  },
  overrides: [
    {
      files: [
        "src/pages/**/*.{ts,tsx}",
        "src/features/**/*.{ts,tsx}",
        "src/widgets/**/*.{ts,tsx}",
      ],
      excludedFiles: ["src/pages/**/use*.ts", "src/pages/**/use*.tsx"],
      rules: {
        "no-restricted-imports": [
          "error",
          {
            paths: [
              {
                name: "@/api/client",
                message:
                  "Do not import apiClient directly in pages/features/widgets. Use domain api modules from src/api.",
              },
            ],
          },
        ],
      },
    },
    {
      files: ["src/api/client.ts"],
      rules: {
        "no-restricted-imports": "off",
      },
    },
  ],
};
