import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('src');
const forbiddenPathFragments = ['/fixtures/', '/fixture/', '/demo/', '/preview/', '/mocks/', '/mock/'];
const forbiddenTokens = [
  /__FIXTURE__/i,
  /DEMO_CASE/i,
  /SYNTHETIC_CASE/i,
  /demoAdapter/i,
  /syntheticAdapter/i,
  /mockCase/i,
  /previewCase/i,
  /\blabCase\b/,
  /p-lab-mode/i,
  /Product Lab case mode/i,
];
const extraTerms = (process.env.PANTA_FORBIDDEN_TERMS ?? '')
  .split(',')
  .map(x => x.trim())
  .filter(Boolean)
  .map(x => new RegExp(x, 'i'));

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]
  );
}

const failures = [];
for (const file of walk(root).filter(f => /\.(ts|tsx|js|jsx|json)$/.test(f))) {
  const rel = '/' + path.relative(process.cwd(), file).replaceAll('\\', '/');
  const text = fs.readFileSync(file, 'utf8');
  if (forbiddenPathFragments.some(x => rel.includes(x))) failures.push(`${rel}: forbidden fixture/demo path`);
  for (const rx of [...forbiddenTokens, ...extraTerms]) {
    if (rx.test(text)) { failures.push(`${rel}: forbidden token ${rx}`); break; }
  }
}

if (failures.length) {
  console.error('Fixture-free gate FAILED:\n' + failures.join('\n'));
  process.exit(1);
}
console.log('Fixture-free gate PASS');
