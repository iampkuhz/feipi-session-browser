// 可选的静态清理诊断：只输出候选，不修改文件，也不作为 Playwright 用例。
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');

const tools = createRequire(path.resolve(process.argv[2], 'package.json'));
const { Linter } = tools('eslint');
const postcss = tools('postcss');
const parseSelector = tools('postcss-selector-parser');
const resources = 'java/web/src/main/resources';
const read = file => fs.readFileSync(file, 'utf8');

// 这些是 classic scripts，共享同一浏览器全局作用域；不能按 ES modules 逐文件判断。
const scripts = ['base.html', 'session.html'].flatMap(template =>
  [...read(`${resources}/templates/${template}`).matchAll(/src="\/static\/(js\/[^"]+)"/g)].map(match => match[1]));
let source = '';
const spans = scripts.map(script => {
  const line = source.split('\n').length;
  source += read(`${resources}/static/${script}`) + '\n;\n';
  return { script, line };
});
for (const result of new Linter().verify(source, {
  languageOptions: { sourceType: 'script' },
  rules: { 'no-unused-vars': ['error', { args: 'none', caughtErrors: 'none' }] },
})) {
  if (result.fatal) throw new Error(result.message);
  const span = spans.findLast(entry => entry.line <= result.line);
  console.log(`JS\t${span.script}:${result.line - span.line + 1}\t${result.message}`);
}

const production = new Set();
const testing = new Set();
const files = execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', 'java'])
  .toString().split('\0');
for (const file of files) {
  if (!/\.(html|java|[cm]?js|ts|peb)$/.test(file) || !fs.existsSync(file)) continue;
  const index = file.includes('/src/main/') && !file.startsWith('java/tests/') ? production : testing;
  for (const token of read(file).match(/[\w-]+/g) || []) index.add(token);
}

const cssDir = `${resources}/static/css/session-detail`;
const sheets = process.argv.slice(3);
for (const file of sheets.length ? sheets : fs.readdirSync(cssDir).filter(name => name.endsWith('.css'))
  .map(name => `${cssDir}/${name}`)) {
  postcss.parse(read(file), { from: file }).walkRules(rule => {
    for (const selector of parseSelector().astSync(rule.selector).nodes) {
      const absent = new Set();
      selector.walkClasses(node => {
        const name = node.value;
        if (name.startsWith('sd-') && !production.has(name)) {
          absent.add(`${name}:${testing.has(name) ? 'test-only' : 'no-literal'}`);
        }
      });
      if (absent.size) {
        console.log(`CSS\t${file}:${rule.source.start.line}\t${selector.toString().trim()}\t${[...absent].join(', ')}`);
      }
    }
  });
}
