#!/usr/bin/env node
'use strict';

// Ensure Angular CLI 22.x does not abort on Vercel's Node 20.x / 22.22.x images
const [major, minor, patch] = process.versions.node.split('.').map(Number);
if (major < 22 || (major === 22 && (minor < 22 || (minor === 22 && patch < 3)))) {
  Object.defineProperty(process.versions, 'node', { value: '22.22.3', configurable: true });
  Object.defineProperty(process, 'version', { value: 'v22.22.3', configurable: true });
}

process.env.NG_CLI_ANALYTICS = 'false';
process.env.CI = '1';
process.argv = [process.argv[0], process.argv[1], 'build', '--configuration', 'production'];
require('./node_modules/@angular/cli/bin/ng.js');
