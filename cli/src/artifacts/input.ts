import { readFile } from 'node:fs/promises'
import process from 'node:process'

export async function readInputText(options: {
  file: string | undefined
  text: string | undefined
  allowStdin?: boolean
  errorMessage: string
}): Promise<string> {
  if (options.text !== undefined) {
    return options.text
  }

  if (options.file) {
    return readFile(options.file, 'utf8')
  }

  if (options.allowStdin && !process.stdin.isTTY) {
    return await readStdin()
  }

  throw new Error(options.errorMessage)
}

async function readStdin(): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const chunks: string[] = []
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (chunk: string) => {
      chunks.push(chunk)
    })
    process.stdin.on('end', () => {
      resolve(chunks.join(''))
    })
    process.stdin.on('error', reject)
  })
}
