export type OutputMode = 'json' | 'raw' | 'text'

export interface CliConfig {
  baseUrl?: string
  sessionToken?: string
  workspaceRoot?: string
}

export interface CliRuntimeOptions {
  baseUrl?: string
  configPath?: string
  json?: boolean
  raw?: boolean
  sessionToken?: string
  workspaceRoot?: string
}

export interface WorkspaceDetection {
  found: boolean
  rootDir: string | null
  manifestPath: string | null
  workbenchDir: string | null
  workspaceName: string | null
}

export interface ArtifactResolution {
  kind: string
  selector: string
  path: string
  exists: boolean
}

export interface CommandFlagManifest {
  name: string
  description: string
  required?: boolean
}

export interface CommandManifestEntry {
  name: string
  description: string
  group: string
  flags?: CommandFlagManifest[]
}

export interface CommandManifestDocument {
  version: string
  package: string
  commands: CommandManifestEntry[]
}

export interface WorkflowTemplateManifest {
  id: string
  name: string
  description: string
  file: string
}

export interface WorkflowTemplateDocument {
  version: string
  templates: WorkflowTemplateManifest[]
}
