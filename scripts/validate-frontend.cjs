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
    const templateStart = whole.match(/<template(?:\s[^>]*)?>/)
    if (!scriptMatch || !templateStart) {
      console.error(`${file}: componente Vue sem <script setup lang="ts"> ou <template>.`)
      failed = true
      continue
    }
    source = scriptMatch[1]
    template = whole.replace(scriptMatch[0], '')
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

// Contrato visual: a navegação ocupa o espaço intermediário; o monitor fica no
// rodapé tanto expandido quanto recolhido. No modo recolhido, o botão de toggle
// não pode disputar largura com o logo.
const sidebarLayoutPath = path.join(sourceRoot, 'assets', 'sidebar-layout.css')
if (!fs.existsSync(sidebarLayoutPath)) {
  console.error(`${sidebarLayoutPath}: contrato de layout da sidebar ausente.`)
  failed = true
} else {
  const css = fs.readFileSync(sidebarLayoutPath, 'utf8')
  if (!/\.sidebar\s+\.sidebar-nav[\s\S]*?flex:\s*1\s+1\s+auto/i.test(css)) {
    console.error(`${sidebarLayoutPath}: sidebar-nav precisa ocupar o espaço flexível restante.`)
    failed = true
  }
  if (!/\.sidebar\s+\.sidebar-monitor[\s\S]*?margin-top:\s*auto/i.test(css)) {
    console.error(`${sidebarLayoutPath}: sidebar-monitor precisa permanecer ancorado no rodapé.`)
    failed = true
  }
  if (!/\.sidebar-is-collapsed\s+\.sidebar\s+\.sidebar-monitor[\s\S]*?display:\s*flex\s*!important/i.test(css)) {
    console.error(`${sidebarLayoutPath}: monitor compacto não pode desaparecer com a sidebar recolhida.`)
    failed = true
  }
  if (!/\.sidebar-is-collapsed\s+\.sidebar\s+\.sidebar-toggle[\s\S]*?position:\s*absolute\s*!important/i.test(css)) {
    console.error(`${sidebarLayoutPath}: toggle recolhido precisa ficar ancorado fora do fluxo do logo.`)
    failed = true
  }
  if (!/\.sidebar-is-collapsed\s+\.sidebar\s+\.sidebar-toggle[\s\S]*?right:\s*-1\.6rem/i.test(css)) {
    console.error(`${sidebarLayoutPath}: toggle recolhido precisa permanecer alinhado à borda direita.`)
    failed = true
  }
}

if (failed) process.exit(1)
console.log(`Frontend: ${checked} scripts TypeScript/Vue validados.`)
