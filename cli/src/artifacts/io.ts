import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'
import { createHash } from 'node:crypto'

export function sha256(content: string | Buffer): string {
  return createHash('sha256').update(content).digest('hex')
}

export async function readTextFile(path: string): Promise<string> {
  return readFile(path, 'utf8')
}

export async function atomicWriteTextFile(
  path: string,
  content: string,
): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  const tempPath = `${path}.${String(process.pid)}.tmp`
  await writeFile(tempPath, content, 'utf8')
  await rename(tempPath, path)
}
