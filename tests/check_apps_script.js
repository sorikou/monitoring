const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const projectRoot = path.resolve(__dirname, '..');
const serverSource = fs.readFileSync(path.join(projectRoot, 'app', 'Code.gs'), 'utf8');
const htmlSource = fs.readFileSync(path.join(projectRoot, 'app', 'Index.html'), 'utf8');
const scriptMatch = htmlSource.match(/<script>([\s\S]*)<\/script>/);

if (!scriptMatch) {
  throw new Error('Index.html にクライアントスクリプトがありません。');
}

new vm.Script(serverSource, { filename: 'Code.gs' });
new vm.Script(scriptMatch[1], { filename: 'Index.html' });
console.log('Apps Script and UI JavaScript syntax OK');
