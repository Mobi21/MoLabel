import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'
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
