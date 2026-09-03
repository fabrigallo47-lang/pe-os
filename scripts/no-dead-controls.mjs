import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const root=path.resolve('src');
const failures=[];
function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);}
for(const file of walk(root).filter(f=>f.endsWith('.tsx'))){
  const source=fs.readFileSync(file,'utf8');
  const sf=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  function visit(node){
    if(ts.isJsxOpeningElement(node)||ts.isJsxSelfClosingElement(node)){
      const tag=node.tagName.getText(sf);
      if(tag==='button'){
        const attrs=new Map();
        for(const p of node.attributes.properties){if(ts.isJsxAttribute(p))attrs.set(p.name.getText(sf),p);}
        const hasAction=attrs.has('onClick')||attrs.has('type')||attrs.has('disabled');
        if(!hasAction){const {line}=sf.getLineAndCharacterOfPosition(node.getStart(sf));failures.push(`${path.relative(process.cwd(),file)}:${line+1} button has no action/disabled contract`);}
      }
    }
    ts.forEachChild(node,visit);
  }
  visit(sf);
}
if(failures.length){console.error('Dead-control gate FAILED:\n'+failures.join('\n'));process.exit(1)}
console.log('Dead-control gate PASS');
