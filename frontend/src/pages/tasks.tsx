import { useState } from 'react'
import {
  ClipboardList,
  Square,
  Tags,
  Plus,
  Pencil,
  Trash2,
  ChevronRight,
  BookOpen,
  AlertCircle,
  ListChecks,
  Eye,
  EyeOff,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { mockTaskSchemas } from '@/mocks/data'
import type { TaskSchema } from '@/mocks/data'

// ── Types ─────────────────────────────────────────────────────────────────────

interface LabelField {
  name: string
  type: 'categorical' | 'numeric' | 'boolean' | 'text' | 'multi_select'
  required: boolean
  config: string
}

interface RubricExample {
  description: string
}

interface RubricEntry {
  label: string
  definition: string
  examples: RubricExample[]
  edgeCases: string[]
}

// ── Mock Detail Data ──────────────────────────────────────────────────────────

const labelFields: LabelField[] = [
  {
    name: 'vehicle_type',
    type: 'categorical',
    required: true,
    config: 'car, truck, bus, motorcycle, bicycle, emergency',
  },
  {
    name: 'vehicle_count',
    type: 'numeric',
    required: true,
    config: 'min: 0, max: 50',
  },
  {
    name: 'is_occluded',
    type: 'boolean',
    required: false,
    config: '\u2014',
  },
  {
    name: 'occlusion_pct',
    type: 'numeric',
    required: false,
    config: 'min: 0, max: 100',
  },
  {
    name: 'confidence_note',
    type: 'text',
    required: false,
    config: 'max: 200 chars',
  },
  {
    name: 'traffic_signs',
    type: 'multi_select',
    required: true,
    config: 'stop, yield, speed_limit_*, no_entry, etc.',
  },
]

const rubricEntries: RubricEntry[] = [
  {
    label: 'car',
    definition:
      'A standard passenger vehicle with four wheels, including sedans, coupes, hatchbacks, SUVs, and station wagons. Must be visible enough to identify the general body shape.',
    examples: [
      {
        description:
          'A white sedan parked at the curb, fully visible from the side profile with all four wheels on the ground.',
      },
      {
        description:
          'A dark-colored SUV moving through an intersection, partially behind a traffic light pole but body shape clearly identifiable.',
      },
    ],
    edgeCases: [
      'Pickup trucks with enclosed cabins should be labeled as "truck" not "car", even if they appear car-sized. The distinguishing factor is the open cargo bed.',
    ],
  },
  {
    label: 'truck',
    definition:
      'A large freight or cargo vehicle, including semi-trucks, box trucks, flatbeds, and pickup trucks with open cargo beds. Must have a clearly distinguishable cargo area separate from the cab.',
    examples: [
      {
        description:
          'A semi-truck with trailer on the highway, viewed from behind. The trailer branding and dual rear axle are visible.',
      },
      {
        description:
          'A white box truck making a delivery, parked with hazard lights on. The cargo box is roughly twice the height of the cab.',
      },
    ],
    edgeCases: [
      'Vans (e.g., large cargo vans like Sprinters) should be labeled as "truck" only if the cargo area is visually distinct from the cabin. Panel vans with unified body should be "car".',
    ],
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

const typeIcon: Record<TaskSchema['type'], typeof Square> = {
  'bounding-box': Square,
  classification: Tags,
  segmentation: Square,
  ner: Tags,
}

const fieldTypeBadgeColor: Record<LabelField['type'], string> = {
  categorical: 'bg-violet-500/10 text-violet-600 border-violet-500/20',
  numeric: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  boolean: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  text: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
  multi_select: 'bg-rose-500/10 text-rose-600 border-rose-500/20',
}

function formatFieldType(type: LabelField['type']): string {
  return type.replace('_', ' ')
}

function formatSchemaType(type: TaskSchema['type']): string {
  return type
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

// ── Sidebar Item ──────────────────────────────────────────────────────────────

function SchemaListItem({
  schema,
  isSelected,
  onSelect,
}: {
  schema: TaskSchema
  isSelected: boolean
  onSelect: () => void
}) {
  const Icon = typeIcon[schema.type]

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors ${
        isSelected
          ? 'border border-primary/40 bg-primary/5'
          : 'border border-transparent hover:bg-muted/50'
      }`}
    >
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
          isSelected ? 'bg-primary/10' : 'bg-muted'
        }`}
      >
        <Icon
          className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`}
        />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={`truncate text-sm font-medium ${
            isSelected ? 'text-foreground' : 'text-foreground/80'
          }`}
        >
          {schema.name}
        </p>
        <div className="mt-1 flex items-center gap-2">
          <Badge
            variant="secondary"
            className="h-5 px-1.5 text-[10px] font-normal"
          >
            {schema.labelCount} labels
          </Badge>
          <Badge
            variant="outline"
            className="h-5 px-1.5 text-[10px] font-normal"
          >
            {formatSchemaType(schema.type)}
          </Badge>
        </div>
      </div>
      <ChevronRight
        className={`h-4 w-4 shrink-0 ${
          isSelected ? 'text-primary' : 'text-muted-foreground/40'
        }`}
      />
    </button>
  )
}

// ── Label Fields Table ────────────────────────────────────────────────────────

function LabelFieldsTable({ fields }: { fields: LabelField[] }) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[180px]">Field Name</TableHead>
            <TableHead className="w-[130px]">Type</TableHead>
            <TableHead className="w-[80px]">Required</TableHead>
            <TableHead>Options / Config</TableHead>
            <TableHead className="w-[90px] text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => (
            <TableRow key={field.name}>
              <TableCell className="font-mono text-sm">{field.name}</TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={`text-[11px] font-normal ${fieldTypeBadgeColor[field.type]}`}
                >
                  {formatFieldType(field.type)}
                </Badge>
              </TableCell>
              <TableCell>
                {field.required ? (
                  <span className="text-sm font-medium text-red-500">*</span>
                ) : (
                  <span className="text-xs text-muted-foreground">no</span>
                )}
              </TableCell>
              <TableCell className="max-w-[260px] truncate text-xs text-muted-foreground">
                {field.config}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7">
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive/70 hover:text-destructive"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// ── Rubric Section ────────────────────────────────────────────────────────────

function RubricSection({ entries }: { entries: RubricEntry[] }) {
  return (
    <Accordion type="multiple" defaultValue={['car']}>
      {entries.map((entry) => (
        <AccordionItem key={entry.label} value={entry.label}>
          <AccordionTrigger className="hover:no-underline">
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="font-mono text-xs">
                {entry.label}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {entry.examples.length} examples, {entry.edgeCases.length} edge{' '}
                {entry.edgeCases.length === 1 ? 'case' : 'cases'}
              </span>
            </div>
          </AccordionTrigger>
          <AccordionContent className="space-y-4 pl-1">
            {/* Definition */}
            <div>
              <div className="mb-1.5 flex items-center gap-1.5">
                <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Definition
                </span>
              </div>
              <p className="text-sm leading-relaxed text-foreground/90">
                {entry.definition}
              </p>
            </div>

            {/* Examples */}
            <div>
              <div className="mb-1.5 flex items-center gap-1.5">
                <ListChecks className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Examples
                </span>
              </div>
              <div className="space-y-2">
                {entry.examples.map((ex, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-border/60 bg-muted/30 px-3 py-2"
                  >
                    <p className="text-sm text-foreground/80">
                      {ex.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* Edge Cases */}
            <div>
              <div className="mb-1.5 flex items-center gap-1.5">
                <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Edge Cases
                </span>
              </div>
              <div className="space-y-2">
                {entry.edgeCases.map((ec, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2"
                  >
                    <p className="text-sm text-foreground/80">{ec}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Edit button */}
            <div className="pt-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-xs"
              >
                <Pencil className="h-3 w-3" />
                Edit Entry
              </Button>
            </div>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function TasksPage() {
  const [selectedId, setSelectedId] = useState(mockTaskSchemas[0]?.id ?? '')
  const [blindReview, setBlindReview] = useState(true)

  const selectedSchema = mockTaskSchemas.find((s) => s.id === selectedId)

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <ClipboardList className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
          <p className="text-sm text-muted-foreground">
            Define and manage labeling task schemas and annotation guidelines.
          </p>
        </div>
      </div>

      {/* ── Body: Sidebar + Detail ──────────────────────────────────────────── */}
      <div className="flex min-h-0 flex-1">
        {/* ── Left Panel: Schema List ────────────────────────────────────────── */}
        <div className="flex w-[320px] shrink-0 flex-col border-r bg-muted/30">
          <div className="px-4 pt-4 pb-2">
            <p className="text-sm font-semibold">Task Schemas</p>
          </div>
          <ScrollArea className="flex-1 px-3">
            <div className="space-y-1 pb-4">
              {mockTaskSchemas.map((schema) => (
                <SchemaListItem
                  key={schema.id}
                  schema={schema}
                  isSelected={schema.id === selectedId}
                  onSelect={() => {
                    setSelectedId(schema.id)
                  }}
                />
              ))}
            </div>
          </ScrollArea>
          <div className="border-t p-3">
            <Button variant="outline" className="w-full gap-2">
              <Plus className="h-4 w-4" />
              New Task Schema
            </Button>
          </div>
        </div>

        {/* ── Right Panel: Schema Detail ─────────────────────────────────────── */}
        <ScrollArea className="flex-1">
          {selectedSchema != null ? (
            <div className="space-y-8 p-6">
              {/* ── Section 1: Schema Overview ───────────────────────────────── */}
              <section>
                <div className="mb-4 flex items-center gap-2">
                  <h2 className="text-lg font-semibold">Schema Overview</h2>
                  <Badge variant="outline" className="font-mono text-xs">
                    v3
                  </Badge>
                </div>

                <Card>
                  <CardContent className="grid gap-5 pt-6">
                    <div className="grid gap-2">
                      <Label htmlFor="schema-name">Name</Label>
                      <Input
                        id="schema-name"
                        defaultValue={selectedSchema.name}
                        className="font-medium"
                      />
                    </div>

                    <div className="grid gap-2">
                      <Label>Type</Label>
                      <div>
                        <Badge className="gap-1.5">
                          {selectedSchema.type === 'bounding-box' ? (
                            <Square className="h-3 w-3" />
                          ) : (
                            <Tags className="h-3 w-3" />
                          )}
                          {formatSchemaType(selectedSchema.type)}
                        </Badge>
                      </div>
                    </div>

                    <div className="grid gap-2">
                      <Label htmlFor="schema-desc">Description</Label>
                      <Textarea
                        id="schema-desc"
                        defaultValue={selectedSchema.description}
                        rows={3}
                        className="resize-none"
                      />
                    </div>
                  </CardContent>
                </Card>
              </section>

              <Separator />

              {/* ── Section 2: Label Fields ──────────────────────────────────── */}
              <section>
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Label Fields</h2>
                  <Badge variant="secondary" className="font-normal">
                    {labelFields.length} fields
                  </Badge>
                </div>

                <LabelFieldsTable fields={labelFields} />

                <div className="mt-3">
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <Plus className="h-3.5 w-3.5" />
                    Add Field
                  </Button>
                </div>
              </section>

              <Separator />

              {/* ── Section 3: Review Configuration ──────────────────────────── */}
              <section>
                <h2 className="mb-4 text-lg font-semibold">
                  Review Configuration
                </h2>

                <Card>
                  <CardContent className="grid gap-6 pt-6">
                    {/* Overlap Policy */}
                    <div className="flex items-center justify-between">
                      <div className="space-y-1">
                        <Label>Overlap Policy</Label>
                        <p className="text-xs text-muted-foreground">
                          Number of independent reviewers per record
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          defaultValue={2}
                          min={1}
                          max={10}
                          className="h-9 w-20 text-center"
                        />
                        <span className="text-sm text-muted-foreground">
                          reviewers per record
                        </span>
                      </div>
                    </div>

                    <Separator />

                    {/* Adjudication Policy */}
                    <div className="flex items-center justify-between">
                      <div className="space-y-1">
                        <Label>Adjudication Policy</Label>
                        <p className="text-xs text-muted-foreground">
                          How disagreements between reviewers are resolved
                        </p>
                      </div>
                      <Select defaultValue="majority">
                        <SelectTrigger className="w-[200px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="majority">
                            Majority vote
                          </SelectItem>
                          <SelectItem value="unanimous">
                            Unanimous agreement
                          </SelectItem>
                          <SelectItem value="senior">
                            Senior reviewer decides
                          </SelectItem>
                          <SelectItem value="manual">
                            Manual adjudication
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <Separator />

                    {/* Blind Review */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                          {blindReview ? (
                            <EyeOff className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <Eye className="h-4 w-4 text-muted-foreground" />
                          )}
                        </div>
                        <div className="space-y-1">
                          <Label>Blind Review</Label>
                          <p className="text-xs text-muted-foreground">
                            Hide agent outputs until reviewer submits their own
                            labels
                          </p>
                        </div>
                      </div>
                      <Switch
                        checked={blindReview}
                        onCheckedChange={setBlindReview}
                      />
                    </div>
                  </CardContent>
                </Card>
              </section>

              <Separator />

              {/* ── Section 4: Rubric ────────────────────────────────────────── */}
              <section>
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold">Rubric</h2>
                    <Badge variant="secondary" className="font-normal">
                      {rubricEntries.length} entries
                    </Badge>
                  </div>
                </div>

                <Card>
                  <CardHeader className="pb-0">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Label definitions, examples, and edge case guidance for
                      reviewers and agents.
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-4">
                    <RubricSection entries={rubricEntries} />
                    <div className="mt-4 border-t pt-4">
                      <Button variant="outline" size="sm" className="gap-1.5">
                        <Plus className="h-3.5 w-3.5" />
                        Add Rubric Entry
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </section>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center p-12">
              <p className="text-sm text-muted-foreground">
                Select a task schema from the list to view its configuration.
              </p>
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}
