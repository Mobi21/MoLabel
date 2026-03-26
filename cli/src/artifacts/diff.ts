export interface ArtifactDiff {
  changed: boolean
  currentHash: string
  candidateHash: string
  currentBytes: number
  candidateBytes: number
  currentPath: string
}

export function diffText(
  current: string,
  candidate: string,
  currentPath: string,
): ArtifactDiff {
  const currentHash = hashLike(current)
  const candidateHash = hashLike(candidate)
  return {
    changed: current !== candidate,
    currentHash,
    candidateHash,
    currentBytes: Buffer.byteLength(current, 'utf8'),
    candidateBytes: Buffer.byteLength(candidate, 'utf8'),
    currentPath,
  }
}

function hashLike(value: string): string {
  let hash = 0
  for (const char of value) {
    hash = Math.imul(31, hash) + (char.codePointAt(0) ?? 0)
  }
  return Math.abs(hash).toString(16)
}
