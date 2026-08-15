const { getDefaultConfig } = require('expo/metro-config');
const config = getDefaultConfig(__dirname);
// Inline requires: defers module evaluation until first use, which measurably
// cuts cold-start time on low-end Android.
config.transformer.getTransformOptions = async () => ({
  transform: { experimentalImportSupport: false, inlineRequires: true },
});
module.exports = config;
