module.exports = function (api) {
  api.cache(true);
  return {
    presets: [['babel-preset-expo', { jsxImportSource: 'react' }]],
    // Reanimated's plugin MUST be last. If it isn't, worklets silently fall
    // back to running on the JS thread and every animation janks -- with no
    // error to tell you why.
    plugins: ['react-native-reanimated/plugin'],
  };
};
