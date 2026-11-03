const expoConfig = require('eslint-config-expo/flat');

module.exports = [
  { ignores: ['.expo/**', 'dist/**', 'web-build/**'] },
  ...expoConfig,
  {
    settings: {
      'import/resolver': {
        typescript: { project: './tsconfig.json' },
        node: { extensions: ['.js', '.jsx', '.ts', '.tsx'] },
      },
    },
  },
];
