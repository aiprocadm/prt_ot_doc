module.exports = {
  ignorePatterns: ["dev-dist/**", "dist/**", "coverage/**"],
  env: {
    browser: true,
    es2021: true
  },
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
    "prettier"
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaFeatures: {
      jsx: true
    },
    ecmaVersion: "latest",
    sourceType: "module"
  },
  plugins: ["react", "@typescript-eslint", "react-hooks", "jsx-a11y"],
  settings: {
    react: {
      version: "detect"
    }
  },
  rules: {
    "react/react-in-jsx-scope": "off",
    "react/prop-types": "off",
    "no-restricted-globals": [
      "error",
      {
        name: "fetch",
        message: "Use apiClient from @/api/client to enforce tenant scoping."
      }
    ],
    "no-restricted-imports": [
      "error",
      {
        paths: [
          {
            name: "axios",
            message: "Use apiClient from @/api/client instead of raw axios."
          }
        ]
      }
    ]
  },
  overrides: [
    {
      files: ["src/api/client.ts"],
      rules: {
        "no-restricted-imports": "off"
      }
    }
  ]
};
