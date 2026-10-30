#!/usr/bin/env node
// example-patch.mjs
//
// ШАБЛОН для патч-скриптов. Скопируй, отредактируй блок
// «=== ТВОИ ПАТЧИ ЗДЕСЬ ===», запусти.
//
// Запуск:
//   node example-patch.mjs                — применить
//   node example-patch.mjs --dry-run      — показать, что было бы сделано
//   node example-patch.mjs --verbose      — больше отладочной информации
//
// Чек-лист перед запуском на реальном проекте:
//   1. node example-patch.mjs --dry-run    — посмотреть план
//   2. node example-patch.mjs              — применить
//   3. node example-patch.mjs              — повторный запуск должен
//      напечатать «всё уже применено» и ничего не изменить
//   4. npx tsc --noEmit                    — проверить типы
//
// ─────────────────────────────────────────────────────────────
// ПРИНЦИПЫ
//
// 1. Идемпотентность.
//    Повторный запуск не должен ничего менять. Каждая операция
//    сначала проверяет, применена ли она уже, и пропускает файл.
//    Это важнее, чем кажется: если патч упал на шаге 5 из 10,
//    после починки ты запустишь его заново — шаги 1–4 должны
//    молча пропуститься, а не примениться ещё раз.
//
// 2. Устойчивость к форматированию.
//    Prettier, editor-on-save и pre-commit хуки меняют отступы,
//    переносят строки, переставляют операнды конкатенации. Поэтому:
//      • не матчи многострочные блоки целиком, если можно
//        матчить одну стабильную строку;
//      • для изменения внутри «подвижного» блока используй
//        replaceBetween с якорями — содержимое между ними может
//        быть отформатировано как угодно;
//      • для замены значения в строке используй replaceLine
//        с regex — regex переживёт смену отступов.
//
// 3. Устойчивость к окончаниям строк.
//    В одном проекте легко встретить смесь LF и CRLF (файлы
//    правились на разных машинах). Все операции нормализуют
//    в LF для матчинга и восстанавливают исходный EOL при
//    записи. Никогда не пиши LF туда, где был CRLF: git
//    покажет весь файл изменённым.
//
// 4. Громкая диагностика.
//    Если паттерн не найден — не «тихо ничего не сделать», а
//    упасть с понятным сообщением: какой файл, какая операция,
//    что искали, что нашли рядом. Тихий no-op хуже ошибки:
//    непонятно, применился патч или нет.
//
// 5. Атомарная запись.
//    Пишем во временный файл и переименовываем. Если процесс
//    упадёт посреди записи, оригинал уцелеет.
//
// 6. Минимум магии.
//    Патч-скрипт — не фреймворк. Одна операция = одно действие.
//    Сложное разбивай на несколько простых.
// ─────────────────────────────────────────────────────────────

import {
  readFileSync,
  writeFileSync,
  existsSync,
  renameSync,
  unlinkSync,
} from 'node:fs'
import { resolve } from 'node:path'

// ─────────────────────────────────────────────────────────────
// CLI и bootstrap
// ─────────────────────────────────────────────────────────────

const ARGS = process.argv.slice(2)
const DRY_RUN = ARGS.includes('--dry-run')
const VERBOSE = ARGS.includes('--verbose')

const root = process.cwd()

if (!existsSync(resolve(root, 'package.json'))) {
  console.error('✗ Запусти из корня проекта (рядом с package.json)')
  process.exit(1)
}

if (DRY_RUN) console.info('ℹ️  dry-run: файлы не будут изменены\n')

// ─────────────────────────────────────────────────────────────
// Счётчики и логирование
// ─────────────────────────────────────────────────────────────

const stats = { created: 0, patched: 0, skipped: 0 }

function ok(msg) {
  console.log(`✓  ${msg}`)
}
function skip(msg) {
  console.log(`⏭  ${msg}`)
  stats.skipped++
}

function fail(rel, label, what, found) {
  console.error(`\n✗  ${label}`)
  console.error(`   Файл: ${rel}`)
  console.error(`   Не найдено: ${what}`)
  if (found !== undefined) {
    console.error(`   Искали: ${JSON.stringify(found).slice(0, 200)}`)
  }
  console.error('\n   Проверь файл вручную. Возможные причины:')
  console.error('   • файл уже правился руками или другим патчем;')
  console.error('   • форматтер переформатировал блок;')
  console.error('   • паттерн не уникален — нужен более длинный якорь.')
  process.exit(1)
}

// ─────────────────────────────────────────────────────────────
// Ядро: чтение / запись с сохранением EOL
// ─────────────────────────────────────────────────────────────

/**
 * Читает файл. Возвращает:
 *   abs — абсолютный путь,
 *   lf  — содержимое с EOL, нормализованным в LF (для матчинга),
 *   eol — исходный EOL ('\n' или '\r\n').
 *
 * Все операции работают в LF-пространстве. Восстановление EOL
 * происходит только при записи.
 */
function readSource(rel) {
  const abs = resolve(root, rel)
  if (!existsSync(abs)) {
    console.error(`✗  Файл не существует: ${rel}`)
    process.exit(1)
  }
  const raw = readFileSync(abs, 'utf8')
  const eol = raw.includes('\r\n') ? '\r\n' : '\n'
  const lf = eol === '\r\n' ? raw.replace(/\r\n/g, '\n') : raw
  if (VERBOSE) console.info(`   читаю ${rel} (EOL=${JSON.stringify(eol)})`)
  return { abs, lf, eol }
}

/**
 * Записывает lf-строку обратно в файл, восстанавливая EOL.
 * Атомарно: temp + rename. В dry-run — только логирует.
 */
function writeSource(abs, lf, eol) {
  const out = eol === '\r\n' ? lf.replace(/\n/g, '\r\n') : lf
  if (DRY_RUN) {
    console.log(`   [dry-run] не записан ${abs}`)
    return
  }
  const tmp = `${abs}.tmp.${process.pid}`
  try {
    writeFileSync(tmp, out, 'utf8')
    renameSync(tmp, abs)
  } catch (err) {
    try {
      unlinkSync(tmp)
    } catch {
      /* ignore */
    }
    throw err
  }
}

/**
 * Показывает контекст вокруг первого «похожего» места — для
 * отладки, когда паттерн не найден. Не падает, просто печатает.
 */
function showContextAround(lf, anchor) {
  let needle
  if (typeof anchor === 'string') {
    needle = anchor.split('\n')[0].trim().slice(0, 40)
  } else {
    needle = anchor.source.slice(0, 40).replace(/[\^$\\]/g, '')
  }
  if (!needle) return
  const lines = lf.split('\n')
  const idx = lines.findIndex((l) => l.includes(needle))
  if (idx < 0) return
  console.error(`   Похожее место (строка ~${idx + 1}):`)
  lines
    .slice(Math.max(0, idx - 1), Math.min(lines.length, idx + 3))
    .forEach((l, i) => console.error(`   ${Math.max(1, idx) + i}: ${l}`))
}

// ─────────────────────────────────────────────────────────────
// Операции
// ─────────────────────────────────────────────────────────────

/**
 * Создать файл, если его нет. Если есть — пропустить.
 * Для «добавляем новый модуль».
 */
function createFile(rel, content) {
  const abs = resolve(root, rel)
  if (existsSync(abs)) {
    skip(`${rel}: уже существует`)
    return false
  }
  if (DRY_RUN) {
    console.log(`   [dry-run] создал бы ${rel}`)
    stats.created++
    return true
  }
  writeFileSync(abs, content, 'utf8')
  ok(`Создан ${rel}`)
  stats.created++
  return true
}

/**
 * Заменить подстроку `from` на `to`. Самая частая операция.
 *
 * Требования:
 *   • `from` встречается ровно один раз (защита от замены не в том
 *     месте). Если нужно иначе — используй replaceLine / regex.
 *   • `to` ещё не присутствует (идемпотентность).
 *
 * Для устойчивости к форматированию:
 *   • предпочитай одну строку многострочному блоку;
 *   • если блок неизбежен — используй replaceBetween.
 */
function replaceOnce(rel, from, to, label) {
  const { abs, lf, eol } = readSource(rel)
  const fromN = from.replace(/\r\n/g, '\n')
  const toN = to.replace(/\r\n/g, '\n')

  if (lf.includes(toN)) {
    skip(`${label}: уже применено`)
    return
  }

  const count = countOccurrences(lf, fromN)
  if (count === 0) {
    showContextAround(lf, fromN)
    fail(rel, label, 'from-паттерн', fromN)
  }
  if (count > 1) {
    console.error(
      `\n✗  ${label}: 'from' встречается ${count} раз — неоднозначно`
    )
    console.error(`   Файл: ${rel}`)
    console.error(`   Искали: ${JSON.stringify(fromN).slice(0, 200)}`)
    console.error(
      '   Сделай паттерн уникальнее (добавь соседнюю строку-якорь).'
    )
    process.exit(1)
  }

  writeSource(abs, lf.replace(fromN, toN), eol)
  ok(label)
  stats.patched++
}

/**
 * Заменить одну строку по regex. Устойчиво к изменению отступов и
 * переформатированию: regex матчит «любую строку, где есть …», а
 * ты заменяешь её целиком.
 *
 * Требования:
 *   • regex матчит ровно одну строку (флаг `m`), если не передан
 *     { all: true };
 *   • replacement — целая строка (включая отступы).
 *
 * Примеры:
 *   replaceLine('src/config.ts',
 *     /^\s*pastDays\s*:\s*\d+\s*,/,
 *     '    pastDays: 7,',
 *     'config: pastDays = 7')
 *
 *   replaceLine('src/foo.ts',
 *     /^import\s+.*\bOldThing\b.*$/,
 *     "import { NewThing } from './new'",
 *     'foo: заменили импорт')
 *
 * Внимание: для удаления строк используй removeLinesMatching,
 * а не replaceLine(..., '', ...) — иначе останется пустая строка
 * и идемпотентность не сработает.
 */
function replaceLine(rel, regex, replacement, label, options = {}) {
  const { abs, lf, eol } = readSource(rel)

  // Идемпотентность: если replacement уже есть как отдельная
  // строка — пропускаем. Для replacement === '' проверка
  // не работает (см. предупреждение выше).
  if (replacement && lf.split('\n').some((l) => l === replacement)) {
    skip(`${label}: уже применено`)
    return
  }

  const baseFlags = regex.flags.replace(/[gy]/g, '') + 'm'
  const allFlags = baseFlags + 'g'

  // Сколько совпадений? Считаем через глобальную версию regex.
  const count = (lf.match(new RegExp(regex.source, allFlags)) ?? []).length
  if (count === 0) {
    showContextAround(lf, regex)
    fail(rel, label, 'regex', regex.toString())
  }
  if (count > 1 && !options.all) {
    console.error(
      `\n✗  ${label}: regex матчит ${count} строк — неоднозначно`
    )
    console.error(`   Файл: ${rel}`)
    console.error(`   Regex: ${regex}`)
    console.error('   Уточни regex или передай { all: true }.')
    process.exit(1)
  }

  const re = new RegExp(regex.source, options.all ? allFlags : baseFlags)
  writeSource(abs, lf.replace(re, replacement), eol)
  ok(label)
  stats.patched++
}

/**
 * Заменить блок между якорями включительно. Содержимое между
 * startAnchor и endAnchor может быть отформатировано как угодно.
 *
 * Якоря — строки (точное вхождение) или regex. Для endAnchor
 * удобно /^}/m — «закрывающая скобка на отдельной строке».
 *
 * Заменяется первое вхождение startAnchor и первый endAnchor
 * после него.
 *
 * Примеры:
 *   replaceBetween('src/lib/warmupState.ts',
 *     'export type WarmupSignature = {',
 *     /^}$/m,
 *     'export type WarmupSignature = {\n  day: string\n  ...\n}',
 *     'warmupState: расширенный тип')
 *
 *   replaceBetween('src/config.ts',
 *     '  warmup: {',
 *     /^  },/m,
 *     '  warmup: {\n    pastDays: 7,\n    ...\n  },',
 *     'config: новый блок warmup')
 */
function replaceBetween(rel, startAnchor, endAnchor, replacement, label) {
  const { abs, lf, eol } = readSource(rel)

  // Идемпотентность: если replacement уже есть целиком — пропускаем.
  // (Грубая проверка, но для типичных случаев работает.)
  if (lf.includes(replacement)) {
    skip(`${label}: уже применено`)
    return
  }

  const start = findAnchor(lf, startAnchor, 0, 'start', rel, label)
  const end = findAnchor(lf, endAnchor, start.end, 'end', rel, label)

  const newLf = lf.slice(0, start.start) + replacement + lf.slice(end.end)
  writeSource(abs, newLf, eol)
  ok(label)
  stats.patched++
}

/**
 * Удалить все строки, матчащие regex. Для чистки мёртвого кода.
 * Идемпотентно по определению: если строк нет — нечего удалять.
 *
 * Пример:
 *   removeLinesMatching('src/lib/offlineSync.ts',
 *     /^\s*const\s+MAX_ATTEMPTS\s*=\s*\d+\s*$/,
 *     'offlineSync: удалён MAX_ATTEMPTS')
 */
function removeLinesMatching(rel, regex, label) {
  const { abs, lf, eol } = readSource(rel)
  // Убираем g-флаг: с ним test() stateful и даёт ложные результаты.
  const re = new RegExp(regex.source, regex.flags.replace('g', ''))
  const lines = lf.split('\n')
  const filtered = lines.filter((l) => !re.test(l))
  if (filtered.length === lines.length) {
    skip(`${label}: нечего удалять`)
    return
  }
  writeSource(abs, filtered.join('\n'), eol)
  ok(`${label} (удалено строк: ${lines.length - filtered.length})`)
  stats.patched++
}

/**
 * Вставить строку после якоря (якорь остаётся). Для чистых
 * добавлений: импорт, новая константа, новый вызов.
 *
 * Пример:
 *   insertAfter('src/lib/offlineSync.ts',
 *     "import { patchLessonCache } from './offlineCachePatch'",
 *     "import { CONFIG } from '../config'",
 *     'offlineSync: импорт CONFIG')
 */
function insertAfter(rel, anchor, line, label) {
  const { abs, lf, eol } = readSource(rel)
  const anchorN = anchor.replace(/\r\n/g, '\n')

  if (lf.includes(anchorN + '\n' + line)) {
    skip(`${label}: уже вставлено`)
    return
  }
  if (!lf.includes(anchorN)) {
    showContextAround(lf, anchorN)
    fail(rel, label, 'anchor', anchorN)
  }
  writeSource(abs, lf.replace(anchorN, anchorN + '\n' + line), eol)
  ok(label)
  stats.patched++
}

// ─────────────────────────────────────────────────────────────
// Вспомогательные
// ─────────────────────────────────────────────────────────────

function countOccurrences(haystack, needle) {
  let count = 0
  let idx = 0
  while ((idx = haystack.indexOf(needle, idx)) !== -1) {
    count++
    idx += needle.length
  }
  return count
}

/**
 * Ищет якорь в тексте, начиная с `from`. Возвращает
 * { start, end } — границы якоря в lf-координатах.
 * anchor — строка (точное вхождение) или regex.
 */
function findAnchor(lf, anchor, from, which, rel, label) {
  if (anchor instanceof RegExp) {
    const flags = anchor.flags.includes('g') ? anchor.flags : anchor.flags + 'g'
    const re = new RegExp(anchor.source, flags)
    re.lastIndex = from
    const m = re.exec(lf)
    if (!m) fail(rel, label, `${which}-anchor (regex)`, anchor.toString())
    return { start: m.index, end: m.index + m[0].length }
  }
  const idx = lf.indexOf(anchor, from)
  if (idx < 0) fail(rel, label, `${which}-anchor`, anchor)
  return { start: idx, end: idx + anchor.length }
}

// ─────────────────────────────────────────────────────────────
// === ТВОИ ПАТЧИ ЗДЕСЬ ===
//
// Раскомментируй нужное и адаптируй под задачу. Примеры
// показывают ровно те случаи, на которых патчи 1–3 спотыкались.
// ─────────────────────────────────────────────────────────────

// ── Пример 1: новый файл-модуль ──────────────────────────────
// createFile(
//   'src/lib/example.ts',
//   `// src/lib/example.ts
// export const EXAMPLE = 1
// `
// )

// ── Пример 2: добавить импорт после существующего ────────────
// insertAfter(
//   'src/lib/offlineSync.ts',
//   "import { patchLessonCache } from './offlineCachePatch'",
//   "import { CONFIG } from '../config'",
//   'offlineSync: импорт CONFIG'
// )

// ── Пример 3: заменить значение в конфиге (regex, устойчиво) ─
// replaceLine(
//   'src/config.ts',
//   /^\s*pastDays\s*:\s*\d+\s*,/,
//   '    pastDays: 7,',
//   'config: pastDays = 7'
// )

// ── Пример 4: заменить блок между якорями (тело функции) ─────
// replaceBetween(
//   'src/lib/foo.ts',
//   'export function hello() {',
//   /^}$/m,
//   'export function hello() {\n  return "world"\n}',
//   'foo: новая hello'
// )

// ── Пример 5: удалить мёртвое объявление ────────────────────
// removeLinesMatching(
//   'src/lib/offlineSync.ts',
//   /^\s*const\s+MAX_ATTEMPTS\s*=\s*\d+\s*$/,
//   'offlineSync: удалён MAX_ATTEMPTS'
// )

// ── Пример 6: заменить использование константы ──────────────
// replaceOnce(
//   'src/lib/offlineSync.ts',
//   'attempts >= MAX_ATTEMPTS',
//   'attempts >= CONFIG.offlineQueue.maxAttempts',
//   'offlineSync: использует CONFIG.offlineQueue.maxAttempts'
// )

// ─────────────────────────────────────────────────────────────
// Итог
// ─────────────────────────────────────────────────────────────

console.log(
  `\n───\nСоздано: ${stats.created} · Изменено: ${stats.patched} · Пропущено: ${stats.skipped}`
)

if (stats.created + stats.patched === 0) {
  if (stats.skipped === 0) {
    console.log(
      '\nℹ️  Это шаблон. Раскомментируй блок «ТВОИ ПАТЧИ ЗДЕСЬ» и запусти снова.'
    )
  } else {
    console.log('\nℹ️  Всё уже применено — патч идемпотентен.')
  }
} else if (!DRY_RUN) {
  console.log('\nПроверь: npx tsc --noEmit')
}