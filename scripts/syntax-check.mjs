import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]).filter(x=>/\.tsx?$/.test(x));}
let bad=0;
for(const file of walk('src')){
  const result=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext},reportDiagnostics:true,fileName:file});
  const errors=(result.diagnostics??[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
  if(errors.length){bad++;console.error(file);errors.forEach(d=>console.error(ts.flattenDiagnosticMessageText(d.messageText,'\n')));}
}
if(bad)process.exit(1);console.log('Syntax transpile PASS');
