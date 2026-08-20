#!/usr/bin/env node
'use strict'

const fs = require('fs')
const path = require('path')

function loadTypeScript() {
  try {
    return require('typescript')
  } catch (_) {
    const candidates = [
      path.resolve(__dirname, '..', 'frontend', 'node_modules', 'typescript', 'lib', 'typescript.js'),
      '/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript/lib/typescript.js',
      '/usr/local/lib/node_modules/typescript/lib/typescript.js',
      '/usr/lib/node_modules/typescript/lib/typescript.js'
    ]
    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) return require(candidate)
    }
    throw new Error('TypeScript não encontrado. Execute npm install no frontend.')
  }
}

const ts = loadTypeScript()
const root = path.resolve(__dirname, '..', 'frontend')
const sourceRoot = path.join(root, 'src')
let failed = false
let checked = 0

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name)
    return entry.isDirectory() ? walk(target) : [target]
  })
}

function reportDiagnostic(file, diagnostic) {
  const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')
  if (typeof diagnostic.start === 'number' && diagnostic.file) {
    const position = diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start)
    console.error(`${file}:${position.line + 1}:${position.character + 1}: ${message}`)
  } else {
    console.error(`${file}: ${message}`)
  }
}

for (const file of walk(sourceRoot).filter((item) =>
  (item.endsWith('.ts') && !item.endsWith('.d.ts')) || item.endsWith('.vue')
)) {
  const whole = fs.readFileSync(file, 'utf8')
  let source = whole
  let template = ''

  if (file.endsWith('.vue')) {
    const scriptMatch = whole.match(/<script\s+setup\s+lang="ts">([\s\S]*?)<\/script>/)
    const templateMatch = whole.match(/<template>([\s\S]*?)<\/template>/)
    if (!scriptMatch || !templateMatch) {
      console.error(`${file}: componente Vue sem <script setup lang="ts"> ou <template>.`)
      failed = true
      continue
    }
    source = scriptMatch[1]
    template = templateMatch[1]
  }

  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      isolatedModules: true
    },
    fileName: file,
    reportDiagnostics: true
  })
  for (const diagnostic of output.diagnostics || []) {
    reportDiagnostic(file, diagnostic)
    failed = true
  }

  const syntaxTree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const imported = []
  for (const statement of syntaxTree.statements) {
    if (!ts.isImportDeclaration(statement) || !statement.importClause) continue
    if (statement.importClause.name) imported.push(statement.importClause.name.text)
    const bindings = statement.importClause.namedBindings
    if (bindings && ts.isNamedImports(bindings)) {
      for (const element of bindings.elements) imported.push(element.name.text)
    }
    if (bindings && ts.isNamespaceImport(bindings)) imported.push(bindings.name.text)
  }

  const usage = new Map(imported.map((name) => [name, 0]))
  function visit(node) {
    if (ts.isImportDeclaration(node)) return
    if (ts.isIdentifier(node) && usage.has(node.text)) usage.set(node.text, usage.get(node.text) + 1)
    ts.forEachChild(node, visit)
  }
  ts.forEachChild(syntaxTree, visit)
  for (const name of imported) {
    const matches = template.match(new RegExp(`\\b${name}\\b`, 'g'))
    if (matches) usage.set(name, usage.get(name) + matches.length)
  }
  const unused = [...usage.entries()].filter(([, count]) => count === 0).map(([name]) => name)
  if (unused.length) {
    console.error(`${file}: imports não utilizados: ${unused.join(', ')}`)
    failed = true
  }
  checked += 1
}

if (failed) process.exit(1)
console.log(`Frontend: ${checked} scripts TypeScript/Vue validados.`)
