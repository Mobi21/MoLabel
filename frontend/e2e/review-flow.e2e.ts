import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { readSeed, type Seed } from './env'

/*
 * Two reviewers label six offline-proposed tickets on an overlap_count 2
 * queue. The first edits ticket-4 to other and ticket-6 to shipping and
 * accepts the rest; the second accepts every proposal. So they disagree on
 * ticket-4 and ticket-6 alone.
 */
const FIRST_EDITS: Record<string, string> = {
  'ticket-4': 'other',
  'ticket-6': 'shipping',
}
const INTENTS = ['refund', 'bug', 'shipping', 'other']
const SHOTS = process.env.MOLABEL_E2E_SCREENSHOTS

let seed: Seed

test.describe.configure({ mode: 'serial' })

test.beforeAll(() => {
  seed = readSeed()
})

async function snap(page: Page, name: string) {
  if (SHOTS) {
    await page.screenshot({
      path: join(SHOTS, `${name}.png`),
      fullPage: true,
      animations: 'disabled',
    })
  }
}

async function signIn(page: Page, name: string) {
  await page.goto('/')
  await expect(page).toHaveURL(/\/sign-in$/)
  await expect(
    page.getByRole('heading', { name: 'Who is reviewing?' }),
  ).toBeVisible()
  await snap(page, 'sign-in')
  const digit = await page
    .getByRole('button', { name: new RegExp(`${name}$|${name} `) })
    .locator('kbd')
    .innerText()
  await page.keyboard.press(digit)
  await expect(page.getByTestId('signed-in-as')).toHaveText(name)
}

async function openQueue(page: Page, title: string) {
  const rows = page.getByTestId('queue-row')
  await expect(rows.first()).toBeVisible()
  const index = (await rows.locator('h2').allInnerTexts()).indexOf(title)
  expect(index).toBeGreaterThanOrEqual(0)
  for (let i = 0; i < index; i++) await page.keyboard.press('j')
  await page.keyboard.press('Enter')
}

/** At the bottom of the page, the key legend leaves the field uncovered. */
async function expectClearOfLegend(page: Page, field: Locator) {
  await page.evaluate(() => {
    window.scrollTo(0, document.documentElement.scrollHeight)
  })
  await expect(field).toBeInViewport()
  const box = await field.boundingBox()
  const legend = await page
    .locator('footer[aria-label="Keyboard shortcuts"]')
    .boundingBox()
  if (!box || !legend) throw new Error('field or legend has no box')
  expect(box.y + box.height).toBeLessThanOrEqual(legend.y)
  await field.click({ timeout: 5_000 })
  await expect(field).toBeFocused()
}

/** Review every item the queue hands this reviewer, by keyboard alone. */
async function reviewAll(page: Page, edits: Record<string, string>) {
  const heading = page.locator('#item-heading')
  const done = page.getByTestId('queue-done')
  const reviewed: string[] = []
  for (;;) {
    await expect(heading.or(done)).toBeVisible()
    if (await done.isVisible()) return reviewed
    const ticket = await heading.innerText()
    await expect(page.getByTestId('ai-proposal')).toBeVisible()
    await expect(page.getByTestId('field-intent')).toHaveAttribute(
      'aria-current',
      'true',
    )
    const edit = edits[ticket]
    if (edit) {
      await page.keyboard.press(String(INTENTS.indexOf(edit) + 1))
      await expect(page.getByTestId('decision-preview')).toHaveText(
        'edit · intent',
      )
    } else {
      await expect(page.getByTestId('decision-preview')).toHaveText(
        'accept · keeps the proposal',
      )
    }
    if (reviewed.length === 0) await snap(page, `review-${ticket}`)
    await page.keyboard.press('Control+Enter')
    await expect(heading.filter({ hasText: ticket })).toHaveCount(0)
    reviewed.push(ticket)
  }
}

test('reviewer 1 reviews every item by keyboard, with edits and accepts', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 1')
  await snap(page, 'queue-list')
  await openQueue(page, 'Ticket triage')

  const reviewed = await reviewAll(page, FIRST_EDITS)
  expect([...reviewed].sort()).toEqual(Object.keys(seed.proposals).sort())

  const last = reviewed.at(-1) ?? ''
  await page.keyboard.press('k')
  await expect(page.locator('#item-heading')).toHaveText(last)
  await expect(page.getByText(/^submitted · (accept|edit)$/)).toBeVisible()
  await page.keyboard.press('k')
  await expect(page.locator('#item-heading')).toHaveText(reviewed.at(-2) ?? '')
  await page.keyboard.press('j')
  await expect(page.locator('#item-heading')).toHaveText(last)
  await page.keyboard.press('j')
  await expect(page.getByTestId('queue-done')).toBeVisible()
})

test('reviewer 2 accepts every proposal, disagreeing on two tickets', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 2')
  await openQueue(page, 'Ticket triage')
  const reviewed = await reviewAll(page, {})
  expect(reviewed).toHaveLength(6)

  await page.keyboard.press('c')
  await expect(page).toHaveURL(/\/calibration$/)
  // Intent, two reviewers on six tickets: refund 5, bug 3, shipping 3, other
  // 1 of n = 12, with ticket-4 and ticket-6 split. D_o = 4/12 and
  // D_e = (144 - 44) / 132, so alpha = 1 - D_o / D_e = 0.560.
  const intent = page.getByTestId('agreement-intent')
  await expect(intent).toContainText('0.560')
  // Against the proposals: 12 reviewer-proposal pairs, the first reviewer's
  // two edits split. Refund 11, bug 7, shipping 5, other 1 of n = 24, so
  // D_o = 4/24, D_e = (576 - 196) / 552, and alpha = 0.758.
  await expect(intent).toContainText('0.758')
  // Pooled over intent, urgent, and the empty note and tags the offline
  // proposals carry: n = 48, D_o = 4/48, D_e = (2304 - 436) / 2256, 0.899.
  await expect(page.getByTestId('alpha-pooled')).toHaveText('α 0.899')
  const skipped = page.getByTestId('skipped-field')
  await expect(skipped.filter({ hasText: 'note' })).toHaveCount(2)
  await expect(skipped.filter({ hasText: 'tags' })).toHaveCount(2)
  await expect(skipped.first()).toContainText(/same label/)
  await snap(page, 'calibration')

  await page.keyboard.press('d')
  await expect(page).toHaveURL(/\/adjudication/)
  const heading = page.locator('#disagreement-heading')
  const ticket = await heading.innerText()
  expect(Object.keys(FIRST_EDITS)).toContain(ticket)
  const column = await page
    .getByTestId('side-by-side')
    .locator('th', { hasText: 'Reviewer 2' })
    .locator('kbd')
    .innerText()
  await page.keyboard.press(column.toLowerCase())
  await snap(page, 'adjudication')
  await page.keyboard.press('Control+Enter')
  const other = Object.keys(FIRST_EDITS).find((t) => t !== ticket) ?? ''
  await expect(heading).toHaveText(other)
  await page.keyboard.press('k')
  await expect(heading).toHaveText(ticket)
  await expect(page.getByTestId('resolution')).toContainText(
    'resolved by Reviewer 2',
  )
  await snap(page, 'adjudication-resolved')

  const base = `/api/v1/adjudication/queues/${seed.queues.overlap}/disagreements`
  const list = (await (await page.request.get(base)).json()) as {
    unresolved: number
    items: { record_id: string; record_external_id: string }[]
  }
  expect(list.unresolved).toBe(1)
  const recordId = list.items.find(
    (i) => i.record_external_id === ticket,
  )?.record_id
  const stored = (await (
    await page.request.get(`${base}/${String(recordId)}`)
  ).json()) as {
    status: string
    resolution: { resolved_labels: { intent: string } }
  }
  expect(stored.status).toBe('resolved')
  expect(stored.resolution.resolved_labels.intent).toBe(
    seed.proposals[ticket]?.intent,
  )
})

test('the resolved record is promoted to gold by keyboard, once', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 2')
  const base = `/api/v1/adjudication/queues/${seed.queues.overlap}/disagreements`
  const list = (await (await page.request.get(base)).json()) as {
    items: { record_id: string; record_external_id: string; status: string }[]
  }
  const resolved = list.items.find((i) => i.status === 'resolved')
  if (!resolved) throw new Error('no resolved disagreement to promote')
  await page.goto(
    `/queues/${seed.queues.overlap}/adjudication?record=${resolved.record_id}`,
  )
  await expect(page.getByTestId('resolution')).toBeVisible()
  const panel = page.getByRole('region', { name: 'Promote to gold' })
  await expect(panel.getByRole('combobox', { name: 'Gold set' })).toHaveValue(
    seed.goldSet,
  )

  await page.keyboard.press('g')
  await expect(panel.getByTestId('promote-result')).toHaveText(
    'Added 1 item to Ticket triage gold, now version 2 with 1 item.',
  )
  await snap(page, 'promote-to-gold')

  const folder = join(seed.workspace, 'gold', seed.goldSet)
  const lines = readFileSync(join(folder, 'gold.jsonl'), 'utf8')
    .split('\n')
    .filter(Boolean)
    .map(
      (line) =>
        JSON.parse(line) as {
          input_ref: { external_id: string }
          expected: { intent: string }
          provenance: { source: string; promoted_by: string }
        },
    )
  expect(lines).toHaveLength(1)
  expect(lines[0]?.input_ref.external_id).toBe(resolved.record_external_id)
  expect(lines[0]?.expected.intent).toBe(
    seed.proposals[resolved.record_external_id]?.intent,
  )
  expect(lines[0]?.provenance.source).toBe('adjudication')
  expect(lines[0]?.provenance.promoted_by).toBe(seed.reviewers.second)
  expect(readFileSync(join(folder, 'gold.yaml'), 'utf8')).toContain(
    'version: 2',
  )

  await page.keyboard.press('g')
  await expect(panel.getByTestId('promote-result')).toContainText(
    'Nothing added to Ticket triage gold; it stays at version 2.',
  )

  const goldPath = join(folder, 'gold.jsonl')
  const promoted = JSON.parse(readFileSync(goldPath, 'utf8')) as {
    expected: { intent: string }
  }
  const handLabel = INTENTS.find((i) => i !== promoted.expected.intent) ?? ''
  writeFileSync(
    goldPath,
    `${JSON.stringify({ ...promoted, expected: { ...promoted.expected, intent: handLabel } })}\n`,
  )
  await page.keyboard.press('g')
  await expect(panel.getByTestId('promote-conflict')).toContainText(
    `gold has ${handLabel}`,
  )
  const conflicts = readFileSync(join(folder, 'conflicts.jsonl'), 'utf8')
    .split('\n')
    .filter(Boolean)
    .map(
      (line) =>
        JSON.parse(line) as {
          existing: { intent: string }
          incoming: { intent: string }
        },
    )
  expect(conflicts.map((c) => [c.existing.intent, c.incoming.intent])).toEqual([
    [handLabel, promoted.expected.intent],
  ])

  await page.goto('/gold')
  await expect(
    page.getByRole('heading', { name: 'Ticket triage gold' }),
  ).toBeVisible()
  await expect(page.getByTestId('gold-version')).toHaveText('version 2')
  await expect(page.getByTestId('gold-item')).toContainText(
    resolved.record_external_id,
  )
  const open = page
    .getByRole('table', { name: 'Open conflicts' })
    .getByTestId('gold-open-conflict')
  await expect(open).toContainText(resolved.record_external_id)
  await expect(open).toContainText(`intent ${handLabel}`)
  await expect(open).toContainText(`intent ${promoted.expected.intent}`)
  await snap(page, 'gold-set')
})

test('a blind queue keeps the AI proposal out of the page until reveal', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 1')
  await openQueue(page, 'Ticket triage, blind')
  const heading = page.locator('#item-heading')
  await expect(heading).toBeVisible()
  const ticket = await heading.innerText()

  await expect(page.getByTestId('ai-proposal-hidden')).toBeVisible()
  await expect(page.getByTestId('ai-proposal')).toHaveCount(0)
  expect(await page.content()).not.toContain('data-testid="ai-proposal"')
  await expect(page.getByTestId('decision-preview')).toHaveText(
    'labels · no proposal shown',
  )
  await page.keyboard.press('Control+Enter')
  await expect(page.getByRole('alert')).toContainText('intent')
  await snap(page, 'blind-before-reveal')

  await page.keyboard.press('r')
  const proposal = page.getByTestId('ai-proposal')
  await expect(proposal).toBeVisible()
  await expect(proposal).toContainText(seed.proposals[ticket]?.intent ?? '')
  await expect(page.getByTestId('decision-preview')).toHaveText(
    'accept · keeps the proposal',
  )
  await page.keyboard.press('Control+Enter')
  await expect(heading.filter({ hasText: ticket })).toHaveCount(0)

  const skipped = await heading.innerText()
  await page.keyboard.press('s')
  await expect(heading.filter({ hasText: skipped })).toHaveCount(0)
  await expect(heading).toBeVisible()
})

test('at phone width the key legend never covers the note or the rationale', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await signIn(page, 'Reviewer 1')
  await openQueue(page, 'Ticket triage, blind')
  await expect(page.locator('#item-heading')).toBeVisible()
  await expectClearOfLegend(page, page.getByRole('textbox', { name: /^Note/ }))
  await snap(page, 'phone-review')

  await page.goto(`/queues/${seed.queues.overlap}/adjudication`)
  await expect(page.locator('#disagreement-heading')).toBeVisible()
  await expectClearOfLegend(
    page,
    page.getByRole('textbox', { name: /^Rationale/ }),
  )
  await snap(page, 'phone-adjudication')
})

/** Label every copy the queue hands the signed-in reviewer, through the API. */
async function labelAll(
  page: Page,
  queueId: string,
  intents: Record<string, string>,
) {
  for (;;) {
    const claim = await page.request.post(`/api/v1/queues/${queueId}/claim`)
    expect(claim.ok()).toBe(true)
    const { task } = (await claim.json()) as {
      task: { id: string; record_external_id: string } | null
    }
    if (task === null) return
    const proposal = seed.proposals[task.record_external_id]
    const submitted = await page.request.post(
      `/api/v1/review-tasks/${task.id}/submit`,
      {
        data: {
          labels: {
            ...proposal,
            intent: intents[task.record_external_id] ?? proposal?.intent,
          },
          auto_claim_next: false,
        },
      },
    )
    expect(submitted.ok()).toBe(true)
  }
}

test('reviewer 1 labels every copy it can claim on a three-copy queue', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 1')
  await labelAll(page, seed.queues.thin, { 'ticket-4': 'other' })
})

test('closing the open copies of a three-copy queue lets two reviewers adjudicate', async ({
  page,
}) => {
  await signIn(page, 'Reviewer 2')
  await labelAll(page, seed.queues.thin, {})

  await page.goto(`/queues/${seed.queues.thin}/adjudication`)
  await expect(
    page.getByText(/6 review copies are still open: 6 unclaimed, 0 claimed/),
  ).toBeVisible()
  await snap(page, 'adjudication-open-copies')
  await page.getByRole('button', { name: 'Close 6 unclaimed copies' }).click()

  await expect(page.locator('#disagreement-heading')).toHaveText('ticket-4')
  await expect(page.getByText('2 reviewers disagree on intent')).toBeVisible()
})
