import tseslint from 'typescript-eslint';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { parser: tseslint.parser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { '@typescript-eslint': tseslint.plugin },
    rules: {
      'no-unreachable': 'error', 'no-debugger': 'error', 'no-constant-condition': ['error', { checkLoops: false }],
      'no-unsafe-finally': 'error', 'no-duplicate-case': 'error',
      '@typescript-eslint/no-floating-promises': 'off'
    }
  }
];
