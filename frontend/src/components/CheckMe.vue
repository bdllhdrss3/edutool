<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, useId, watch } from 'vue'
import { ArrowUpRight, Check, ChevronLeft, ChevronRight, Eye, FileQuestion, RefreshCw } from '@lucide/vue'
import { api, type QuizQuestion, type QuizResult } from '../api'

const props = defineProps<{ documentId: number; pageCount: number; currentPage: number }>()
const emit = defineEmits<{ openPage: [page: number]; error: [message: string] }>()
const id = useId()
const PAGE_LIMIT = 100
const PAGE_WINDOW = 50
const selectedPages = ref<number[]>([])
const draftPages = ref<number[]>([])
const rangeStart = ref<number | string>(1)
const rangeEnd = ref<number | string>(1)
const pageWindow = ref(0)
const questions = ref<QuizQuestion[]>([])
const answers = ref<Record<number, number>>({})
const revealed = ref<number[]>([])
const currentIndex = ref(0)
const busy = ref(false)
const submitted = ref(false)
const scopeChosen = ref(false)
const pageDialog = ref<HTMLDialogElement | null>(null)
const confirmDialog = ref<HTMLDialogElement | null>(null)
const questionHeading = ref<HTMLElement | null>(null)
const scrollBody = ref<HTMLElement | null>(null)
type Confirmation = 'submit' | 'reveal' | 'reset' | 'regenerate'
const confirmation = ref<Confirmation>('submit')
let controller: AbortController | null = null
let requestVersion = 0
let disposed = false

const totalPages = computed(() => Number.isFinite(props.pageCount) ? Math.max(0, Math.floor(props.pageCount)) : 0)
const readerPage = computed(() => Math.min(totalPages.value, Math.max(1, Math.floor(props.currentPage) || 1)))
const currentQuestion = computed(() => questions.value[currentIndex.value])
const answeredCount = computed(() => Object.keys(answers.value).length)
const unansweredCount = computed(() => questions.value.length - answeredCount.value)
const showingAnswer = computed(() => submitted.value || revealed.value.includes(currentIndex.value))
const score = computed(() => questions.value.reduce((total, question, index) =>
  total + (answers.value[index] === question.correct_index && !revealed.value.includes(index) ? 1 : 0), 0))
const pageWindowCount = computed(() => Math.ceil(totalPages.value / PAGE_WINDOW))
const visiblePages = computed(() => {
  const first = pageWindow.value * PAGE_WINDOW + 1
  return Array.from({ length: Math.max(0, Math.min(PAGE_WINDOW, totalPages.value - first + 1)) }, (_, i) => first + i)
})
const sourceSummary = computed(() => summarizePages(selectedPages.value))
const confirmationCopy = computed(() => {
  switch (confirmation.value) {
    case 'submit': return {
      title: 'Submit with unanswered questions?',
      body: `${unansweredCount.value} ${unansweredCount.value === 1 ? 'question is' : 'questions are'} unanswered. These receive no credit. You can still review every explanation after submitting.`,
      action: 'Submit anyway',
    }
    case 'reveal': return {
      title: 'See the reasoning first?',
      body: 'Revealing the answer locks this question and gives it no credit, even if your selected answer is correct. Use it to understand the concept, then keep going.',
      action: 'Reveal answer',
    }
    case 'reset': return {
      title: 'Reset this practice?',
      body: 'Your questions, answers and score will be cleared. Your chosen source pages will stay selected.',
      action: 'Reset practice',
    }
    case 'regenerate': return {
      title: 'Try a fresh set?',
      body: 'Generate new questions from the same pages. This replaces your current practice only when the new questions are ready.',
      action: 'Generate new set',
    }
  }
})

function summarizePages(pages: number[]) {
  if (!pages.length) return 'No pages selected'
  const ranges: string[] = []
  let start = pages[0]!
  let end = start
  for (const page of pages.slice(1)) {
    if (page === end + 1) end = page
    else {
      ranges.push(start === end ? `${start}` : `${start}-${end}`)
      start = end = page
    }
  }
  ranges.push(start === end ? `${start}` : `${start}-${end}`)
  return `${pages.length === 1 ? 'Page' : 'Pages'} ${ranges.join(', ')}`
}

function clearPractice() {
  questions.value = []
  answers.value = {}
  revealed.value = []
  currentIndex.value = 0
  submitted.value = false
}

function invalidateRequest() {
  requestVersion++
  controller?.abort()
  controller = null
  busy.value = false
}

function closeDialogs() {
  pageDialog.value?.close()
  confirmDialog.value?.close()
}

// Reset the scope for a new document; explicit selections stay stable while reading.
watch(() => props.documentId, () => {
  invalidateRequest()
  closeDialogs()
  clearPractice()
  scopeChosen.value = false
  selectedPages.value = readerPage.value > 0 ? [readerPage.value] : []
  draftPages.value = []
}, { immediate: true })

watch(readerPage, value => {
  if (!scopeChosen.value && !questions.value.length && !busy.value && !pageDialog.value?.open) {
    selectedPages.value = value > 0 ? [value] : []
  }
})

// Accommodate a document whose page count arrives after its ID, without losing a selection.
watch(totalPages, (count, previous) => {
  if (!previous && count && !selectedPages.value.length && !questions.value.length && !busy.value) {
    selectedPages.value = [readerPage.value]
  }
})

onDeactivated(closeDialogs)
onBeforeUnmount(() => {
  disposed = true
  invalidateRequest()
  closeDialogs()
})

function openPagePicker() {
  if (busy.value || !totalPages.value || pageDialog.value?.open) return
  draftPages.value = [...selectedPages.value]
  rangeStart.value = selectedPages.value[0] ?? readerPage.value
  rangeEnd.value = selectedPages.value[selectedPages.value.length - 1] ?? readerPage.value
  pageWindow.value = Math.floor((Number(rangeStart.value) - 1) / PAGE_WINDOW)
  pageDialog.value?.showModal()
}

function togglePage(page: number) {
  if (busy.value) return
  if (draftPages.value.includes(page)) draftPages.value = draftPages.value.filter(item => item !== page)
  else if (draftPages.value.length < PAGE_LIMIT) draftPages.value = [...draftPages.value, page].sort((a, b) => a - b)
}

function useCurrentPage() {
  if (busy.value || !readerPage.value) return
  draftPages.value = [readerPage.value]
  rangeStart.value = rangeEnd.value = readerPage.value
  pageWindow.value = Math.floor((readerPage.value - 1) / PAGE_WINDOW)
}

function selectAllPages() {
  if (busy.value) return
  draftPages.value = Array.from({ length: Math.min(totalPages.value, PAGE_LIMIT) }, (_, i) => i + 1)
  pageWindow.value = 0
}

function selectRange() {
  if (busy.value) return
  const start = Number(rangeStart.value)
  const end = Number(rangeEnd.value)
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > totalPages.value) {
    emit('error', `Choose a whole-number range between 1 and ${totalPages.value}, with the last page at or after the first.`)
    return
  }
  if (end - start + 1 > PAGE_LIMIT) {
    emit('error', 'Choose a range of at most 100 pages.')
    return
  }
  draftPages.value = Array.from({ length: end - start + 1 }, (_, i) => start + i)
  pageWindow.value = Math.floor((start - 1) / PAGE_WINDOW)
}

function applyPages() {
  if (busy.value || !draftPages.value.length || draftPages.value.length > PAGE_LIMIT) return
  if (draftPages.value.some(page => page < 1 || page > totalPages.value)) {
    emit('error', 'The source pages have changed. Please select pages from this document again.')
    return
  }
  const changed = draftPages.value.join(',') !== selectedPages.value.join(',')
  scopeChosen.value = true
  selectedPages.value = [...draftPages.value]
  if (changed) clearPractice()
  pageDialog.value?.close()
}

async function focusQuestion() {
  await nextTick()
  if (disposed) return
  if (scrollBody.value) scrollBody.value.scrollTop = 0
  // A finished background request must not steal focus from another parent tab.
  if (questionHeading.value?.getClientRects().length) questionHeading.value.focus({ preventScroll: true })
}

async function generate() {
  if (busy.value || disposed || !selectedPages.value.length) return
  if (selectedPages.value.length > PAGE_LIMIT || selectedPages.value.some(page => page < 1 || page > totalPages.value)) {
    emit('error', 'Select between 1 and 100 valid source pages before starting.')
    return
  }
  const version = ++requestVersion
  scopeChosen.value = true
  const documentId = props.documentId
  const pages = [...selectedPages.value]
  const requestController = new AbortController()
  controller = requestController
  busy.value = true
  try {
    const result = await api<QuizResult>(`/documents/${documentId}/quiz`, {
      method: 'POST', signal: requestController.signal,
      body: JSON.stringify({ page_numbers: pages, question_count: 10 }),
    })
    if (disposed || version !== requestVersion || documentId !== props.documentId) return
    if (!Array.isArray(result?.questions) || result.questions.length !== 10 ||
      !result.questions.every(question => question && typeof question.question === 'string' && question.question.trim() &&
        Array.isArray(question.options) && question.options.length === 4 &&
        question.options.every(option => typeof option === 'string' && option.trim()) &&
        Number.isInteger(question.correct_index) && question.correct_index >= 0 && question.correct_index < 4 &&
        typeof question.explanation === 'string' && question.explanation.trim() && pages.includes(question.source_page))) {
      throw new Error('The quiz response was incomplete. Try generating a fresh set.')
    }
    clearPractice()
    questions.value = result.questions
    await focusQuestion()
  } catch (exception) {
    if (disposed || version !== requestVersion || requestController.signal.aborted || documentId !== props.documentId) return
    emit('error', exception instanceof Error ? exception.message : 'Could not prepare your questions. Please try again.')
  } finally {
    if (version === requestVersion) {
      busy.value = false
      controller = null
    }
  }
}

function selectAnswer(index: number) {
  if (busy.value || showingAnswer.value || !currentQuestion.value) return
  answers.value[currentIndex.value] = index
}

function goToQuestion(index: number) {
  if (busy.value || index < 0 || index >= questions.value.length) return
  currentIndex.value = index
  void focusQuestion()
}

function questionStatus(index: number) {
  if (revealed.value.includes(index)) return 'Revealed, no credit'
  if (submitted.value) {
    if (answers.value[index] === undefined) return 'Unanswered'
    return answers.value[index] === questions.value[index]?.correct_index ? 'Correct' : 'Needs revision'
  }
  return answers.value[index] === undefined ? 'Unanswered' : 'Answered'
}

async function askConfirmation(action: Confirmation) {
  if (busy.value || !questions.value.length || confirmDialog.value?.open) return
  if ((action === 'submit' && submitted.value) || (action === 'reveal' && showingAnswer.value)) return
  if (action === 'submit' && !unansweredCount.value) {
    submitted.value = true
    void focusQuestion()
    return
  }
  confirmation.value = action
  const version = requestVersion
  await nextTick()
  if (!disposed && version === requestVersion && questions.value.length) confirmDialog.value?.showModal()
}

function confirmAction() {
  if (busy.value || !questions.value.length) return
  confirmDialog.value?.close()
  switch (confirmation.value) {
    case 'submit': submitted.value = true; void focusQuestion(); break
    case 'reveal':
      if (!showingAnswer.value) revealed.value = [...revealed.value, currentIndex.value]
      void focusQuestion()
      break
    case 'reset': clearPractice(); break
    case 'regenerate': void generate(); break
  }
}
</script>

<template>
  <section class="quiz-panel" :aria-labelledby="`${id}-title`" :aria-busy="busy">
    <header class="quiz-header">
      <div class="quiz-title-row">
        <h2 :id="`${id}-title`"><FileQuestion :size="19" aria-hidden="true" /> Check me</h2>
        <span class="quiz-caption">{{ submitted ? 'Review' : questions.length ? 'Practice' : 'Concept practice' }}</span>
      </div>
      <div class="quiz-source-row">
        <span class="quiz-source" :title="sourceSummary"><span class="quiz-muted">Source</span> {{ sourceSummary }}</span>
        <button class="quiz-button quiz-text-button" type="button" :disabled="busy || !totalPages" @click="openPagePicker">Change pages</button>
      </div>
      <template v-if="questions.length">
        <div class="quiz-progress-copy" role="status" aria-live="polite">
          <strong v-if="submitted">{{ score }} / {{ questions.length }} earned</strong>
          <strong v-else>{{ answeredCount }} / {{ questions.length }} answered</strong>
          <span>{{ revealed.length ? `${revealed.length} revealed, no credit` : submitted ? 'Review the reasoning below' : 'Take your time' }}</span>
        </div>
        <progress class="quiz-progress" :value="submitted ? score : answeredCount" :max="questions.length" :aria-label="submitted ? 'Earned score' : 'Questions answered'" />
        <nav class="quiz-pagination" aria-label="Quiz questions">
          <button v-for="(_, index) in questions" :key="index" class="quiz-index" type="button"
            :class="{ 'is-current': currentIndex === index, 'is-answered': answers[index] !== undefined, 'is-revealed': revealed.includes(index), 'is-correct': submitted && answers[index] === questions[index]?.correct_index && !revealed.includes(index) }"
            :aria-current="currentIndex === index ? 'step' : undefined" :aria-label="`Question ${index + 1}: ${questionStatus(index)}`"
            :title="`Question ${index + 1}: ${questionStatus(index)}`" :disabled="busy" @click="goToQuestion(index)">
            {{ index + 1 }}<span class="quiz-index-marker" aria-hidden="true">{{ revealed.includes(index) ? '?' : answers[index] !== undefined ? '•' : '' }}</span>
          </button>
        </nav>
      </template>
    </header>

    <div ref="scrollBody" class="quiz-body" tabindex="0" :aria-label="questions.length ? 'Question and explanation' : 'About concept practice'">
      <div v-if="!questions.length" class="quiz-intro">
        <div class="quiz-intro-mark" aria-hidden="true"><FileQuestion :size="30" :stroke-width="1.5" /></div>
        <h3>Make the ideas stick.</h3>
        <p>Test what you understand, not just what you remember. Work through ten questions, then revisit the reasoning.</p>
        <ol class="quiz-method">
          <li><strong>Think it through</strong><span>Choose the answer that best fits the concept.</span></li>
          <li><strong>Learn from the gaps</strong><span>Review explanations and return to the source.</span></li>
        </ol>
        <p class="quiz-caption">Need a hint? Revealing an answer gives up credit for that question.</p>
      </div>
      <article v-else-if="currentQuestion" :key="currentIndex" class="quiz-question">
        <div class="quiz-question-meta"><span>Question {{ currentIndex + 1 }} of {{ questions.length }}</span><span>{{ questionStatus(currentIndex) }}</span></div>
        <h3 :id="`${id}-question`" ref="questionHeading" class="quiz-question-title" tabindex="-1">{{ currentQuestion.question }}</h3>
        <fieldset class="quiz-options" :disabled="busy || showingAnswer" :aria-labelledby="`${id}-question`">
          <legend class="quiz-sr-only">Choose one answer</legend>
          <label v-for="(option, index) in currentQuestion.options" :key="index" class="quiz-option"
            :class="{ 'is-selected': answers[currentIndex] === index, 'is-correct': showingAnswer && index === currentQuestion.correct_index, 'is-incorrect': showingAnswer && answers[currentIndex] === index && index !== currentQuestion.correct_index }">
            <input type="radio" :name="`${id}-answer-${currentIndex}`" :value="index" :checked="answers[currentIndex] === index" @change="selectAnswer(index)" />
            <span class="quiz-option-letter" aria-hidden="true">{{ String.fromCharCode(65 + index) }}</span>
            <span class="quiz-option-copy">{{ option }}<span v-if="showingAnswer && index === currentQuestion.correct_index" class="quiz-option-note"><Check :size="14" aria-hidden="true" /> Correct answer</span><span v-else-if="showingAnswer && answers[currentIndex] === index" class="quiz-option-note">Your answer</span></span>
          </label>
        </fieldset>
        <section v-if="showingAnswer" class="quiz-explanation" :aria-labelledby="`${id}-reasoning`">
          <h4 :id="`${id}-reasoning`">Why this answer works</h4>
          <p>{{ currentQuestion.explanation }}</p>
          <p v-if="revealed.includes(currentIndex)" class="quiz-caption">Revealed for learning. No credit earned on this question.</p>
          <button class="quiz-button quiz-text-button" type="button" :disabled="busy" @click="emit('openPage', currentQuestion.source_page)">Revisit page {{ currentQuestion.source_page }} <ArrowUpRight :size="15" aria-hidden="true" /></button>
        </section>
      </article>
    </div>

    <footer class="quiz-footer">
      <p v-if="busy" class="quiz-loading" role="status">Preparing questions that connect the ideas…</p>
      <button v-if="!questions.length" class="quiz-button quiz-primary quiz-start" type="button" :disabled="busy || !selectedPages.length" @click="generate"><RefreshCw v-if="busy" :size="16" aria-hidden="true" />{{ busy ? 'Preparing practice…' : 'Start 10 questions' }}<ChevronRight v-if="!busy" :size="16" aria-hidden="true" /></button>
      <template v-else>
        <div class="quiz-navigation">
          <button class="quiz-button" type="button" :disabled="busy || currentIndex === 0" @click="goToQuestion(currentIndex - 1)"><ChevronLeft :size="16" aria-hidden="true" /> Previous</button>
          <button v-if="!submitted" class="quiz-button quiz-text-button" type="button" :disabled="busy || showingAnswer" @click="askConfirmation('reveal')"><Eye :size="16" aria-hidden="true" /> Show answer</button>
          <button class="quiz-button" type="button" :disabled="busy || currentIndex === questions.length - 1" @click="goToQuestion(currentIndex + 1)">Next <ChevronRight :size="16" aria-hidden="true" /></button>
        </div>
        <div class="quiz-finish-row">
          <button class="quiz-button quiz-text-button" type="button" :disabled="busy" @click="askConfirmation('reset')">Reset</button>
          <button v-if="submitted" class="quiz-button quiz-primary" type="button" :disabled="busy" @click="askConfirmation('regenerate')"><RefreshCw :size="15" aria-hidden="true" />{{ busy ? 'Preparing…' : 'New questions' }}</button>
          <button v-else class="quiz-button quiz-primary" type="button" :disabled="busy" @click="askConfirmation('submit')">Submit practice <Check :size="16" aria-hidden="true" /></button>
        </div>
      </template>
    </footer>

    <dialog ref="pageDialog" class="quiz-dialog" :aria-labelledby="`${id}-pages-title`" :aria-describedby="`${id}-pages-description`" @keydown.esc.stop @cancel.stop>
      <form class="quiz-dialog-frame" novalidate @submit.prevent="applyPages">
        <header class="quiz-dialog-header">
          <h3 :id="`${id}-pages-title`">Choose your source pages</h3>
          <p :id="`${id}-pages-description`">Focus on one idea or connect a whole section. Select up to 100 pages.</p>
        </header>
        <div class="quiz-dialog-body">
          <div class="quiz-page-shortcuts">
            <button class="quiz-button" type="button" :disabled="busy" @click="useCurrentPage">Current page {{ readerPage }}</button>
            <button class="quiz-button" type="button" :disabled="busy" @click="selectAllPages">{{ totalPages > PAGE_LIMIT ? 'Select first 100' : 'Select all' }}</button>
            <button class="quiz-button quiz-text-button" type="button" :disabled="busy || !draftPages.length" @click="draftPages = []">Clear</button>
          </div>
          <fieldset class="quiz-range" :disabled="busy" @keydown.enter.prevent="selectRange">
            <legend>Replace selection with a range</legend>
            <label>From<input v-model="rangeStart" type="number" min="1" :max="totalPages" step="1" inputmode="numeric" /></label>
            <label>To<input v-model="rangeEnd" type="number" min="1" :max="totalPages" step="1" inputmode="numeric" /></label>
            <button class="quiz-button" type="button" @click="selectRange">Use range</button>
          </fieldset>
          <div class="quiz-page-count" role="status">{{ draftPages.length }} / 100 selected<span v-if="draftPages.length === PAGE_LIMIT">Limit reached. Deselect a page to add another.</span></div>
          <fieldset class="quiz-page-grid" :disabled="busy">
            <legend class="quiz-sr-only">Toggle individual source pages</legend>
            <label v-for="page in visiblePages" :key="page" class="quiz-page" :class="{ 'is-selected': draftPages.includes(page) }">
              <input type="checkbox" :checked="draftPages.includes(page)" :aria-label="`Page ${page}${page === readerPage ? ', current reader page' : ''}`" :disabled="!draftPages.includes(page) && draftPages.length >= PAGE_LIMIT" @change="togglePage(page)" />
              <span>{{ page }}</span>
            </label>
          </fieldset>
          <nav v-if="pageWindowCount > 1" class="quiz-page-browse" aria-label="Browse source pages">
            <button class="quiz-button" type="button" :disabled="busy || pageWindow === 0" aria-label="Previous source pages" @click="pageWindow--"><ChevronLeft :size="16" aria-hidden="true" /></button>
            <span>Pages {{ visiblePages[0] }}-{{ visiblePages[visiblePages.length - 1] }} of {{ totalPages }}</span>
            <button class="quiz-button" type="button" :disabled="busy || pageWindow >= pageWindowCount - 1" aria-label="Next source pages" @click="pageWindow++"><ChevronRight :size="16" aria-hidden="true" /></button>
          </nav>
          <p v-if="questions.length" class="quiz-caption">Applying different pages clears this practice and its answers. Cancel keeps everything as it is.</p>
        </div>
        <footer class="quiz-dialog-footer">
          <button class="quiz-button" type="button" autofocus @click="pageDialog?.close()">Cancel</button>
          <button class="quiz-button quiz-primary" type="submit" :disabled="busy || !draftPages.length">Apply pages</button>
        </footer>
      </form>
    </dialog>

    <dialog ref="confirmDialog" class="quiz-dialog quiz-confirm-dialog" :aria-labelledby="`${id}-confirm-title`" :aria-describedby="`${id}-confirm-description`" @keydown.esc.stop @cancel.stop>
      <div class="quiz-dialog-frame">
        <header class="quiz-dialog-header"><h3 :id="`${id}-confirm-title`">{{ confirmationCopy.title }}</h3></header>
        <div class="quiz-dialog-body"><p :id="`${id}-confirm-description`">{{ confirmationCopy.body }}</p></div>
        <footer class="quiz-dialog-footer">
          <button class="quiz-button" type="button" autofocus @click="confirmDialog?.close()">Cancel</button>
          <button class="quiz-button quiz-primary" type="button" :disabled="busy" @click="confirmAction">{{ confirmationCopy.action }}</button>
        </footer>
      </div>
    </dialog>
  </section>
</template>

<style scoped>
/* Local names keep the quiz independent of the parent's in-progress layout styles. */
.quiz-panel {
  --quiz-ink: var(--color-fg, #134e4a);
  --quiz-muted: var(--color-muted-fg, #475569);
  --quiz-surface: var(--color-card, #fff);
  --quiz-line: var(--color-border, #cfe7e2);
  --quiz-accent: var(--color-primary-hover, #0b7f75);
  --quiz-tint: color-mix(in srgb, var(--quiz-accent) 7%, var(--quiz-surface));
  display: flex;
  flex-direction: column;
  flex: 1 1 0%;
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  color: var(--quiz-ink);
  font: 14px/1.55 var(--font-ui, system-ui, sans-serif);
  container-type: inline-size;
}
.quiz-panel :where(h2, h3, h4, p, fieldset, ol) { margin: 0; }
.quiz-panel :where(button, input) { font: inherit; }
.quiz-panel :where(button, input):focus-visible { outline: 2px solid var(--quiz-accent); outline-offset: 3px; }
.quiz-panel :where(button):disabled { cursor: not-allowed; opacity: .48; }
.quiz-panel :where(svg) { flex-shrink: 0; }
.quiz-header, .quiz-footer { flex: 0 0 auto; display: flex; flex-direction: column; gap: 12px; }
.quiz-header { height: auto; align-items: stretch; justify-content: flex-start; padding: 2px 2px 16px; border-bottom: 1px solid var(--quiz-line); }
.quiz-title-row, .quiz-source-row, .quiz-progress-copy, .quiz-question-meta, .quiz-navigation, .quiz-finish-row, .quiz-page-browse { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 0; }
.quiz-title-row h2 { display: flex; align-items: center; gap: 10px; font-size: 19px; line-height: 1.3; letter-spacing: -.4px; }
.quiz-caption, .quiz-muted, .quiz-question-meta { color: var(--quiz-muted); font-size: 12px; line-height: 1.5; }
.quiz-source { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.quiz-source .quiz-muted { margin-right: 6px; }
.quiz-source-row > button { flex-shrink: 0; }
.quiz-button { display: inline-flex; justify-content: center; align-items: center; gap: 6px; width: auto; min-height: 36px; margin: 0; padding: 8px 12px; border: 1px solid var(--quiz-line); border-radius: 8px; background: var(--quiz-surface); color: var(--quiz-ink); font-size: 12px; font-weight: 600; line-height: 1.3; text-decoration: none; white-space: nowrap; cursor: pointer; }
.quiz-button:hover:not(:disabled) { background: var(--quiz-tint); border-color: var(--quiz-accent); }
.quiz-button:active:not(:disabled) { transform: translateY(1px); }
.quiz-primary { background: var(--quiz-accent); border-color: var(--quiz-accent); color: #fff; }
.quiz-primary:hover:not(:disabled) { background: color-mix(in srgb, var(--quiz-accent) 86%, #102b29); color: #fff; }
.quiz-text-button { padding-inline: 4px; border-color: transparent; background: transparent; color: var(--quiz-accent); }
.quiz-text-button:hover:not(:disabled) { border-color: transparent; }
.quiz-progress-copy { align-items: baseline; font-size: 12px; }
.quiz-progress-copy > span { color: var(--quiz-muted); text-align: right; }
.quiz-progress { appearance: none; display: block; width: 100%; height: 4px; border: 0; border-radius: 4px; overflow: hidden; background: var(--quiz-tint); color: var(--quiz-accent); }
.quiz-progress::-webkit-progress-bar { background: var(--quiz-tint); }
.quiz-progress::-webkit-progress-value { background: var(--quiz-accent); }
.quiz-progress::-moz-progress-bar { background: var(--quiz-accent); }
.quiz-pagination { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 5px; }
.quiz-index { position: relative; display: grid; place-items: center; min-width: 0; min-height: 34px; padding: 3px 0 7px; border: 1px solid var(--quiz-line); border-radius: 6px; background: var(--quiz-surface); color: var(--quiz-muted); font-size: 12px; font-variant-numeric: tabular-nums; cursor: pointer; }
.quiz-index.is-answered { background: var(--quiz-tint); color: var(--quiz-ink); }
.quiz-index.is-correct { border-color: var(--quiz-accent); }
.quiz-index.is-revealed { border-style: dashed; }
.quiz-index.is-current { background: var(--quiz-accent); border-color: var(--quiz-accent); color: #fff; font-weight: 700; }
.quiz-index-marker { position: absolute; bottom: 0; font-size: 9px; line-height: 10px; }
.quiz-body { flex: 1 1 0%; min-height: 0; min-width: 0; overflow: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: var(--quiz-line) transparent; padding: 22px 4px 24px 2px; overflow-wrap: anywhere; }
.quiz-body:focus-visible { outline: 2px solid var(--quiz-accent); outline-offset: -2px; }
.quiz-intro { display: flex; flex-direction: column; align-items: flex-start; gap: 18px; max-width: 52ch; padding: 8px 0; }
.quiz-intro-mark { display: grid; place-items: center; width: 58px; height: 58px; border-radius: 16px; background: var(--quiz-tint); color: var(--quiz-accent); }
.quiz-intro h3 { font-size: clamp(23px, 6cqi, 30px); font-weight: 650; letter-spacing: -.8px; line-height: 1.2; }
.quiz-intro > p { color: var(--quiz-muted); }
.quiz-method { display: flex; flex-direction: column; gap: 16px; padding: 0; list-style: none; }
.quiz-method li { padding-left: 14px; border-left: 2px solid var(--quiz-line); }
.quiz-method strong, .quiz-method span { display: block; }
.quiz-method strong { font-size: 13px; }
.quiz-method span { color: var(--quiz-muted); font-size: 12px; }
.quiz-question { display: flex; flex-direction: column; gap: 20px; }
.quiz-question-meta { flex-wrap: wrap; gap: 10px; font-variant-numeric: tabular-nums; }
.quiz-question-title { font-size: clamp(17px, 4.6cqi, 21px); font-weight: 600; line-height: 1.5; letter-spacing: -.25px; white-space: pre-wrap; }
.quiz-question-title:focus { outline: none; }
.quiz-question-title:focus-visible { outline: 2px solid var(--quiz-line); outline-offset: 4px; border-radius: 4px; }
.quiz-options { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 0; border: 0; }
.quiz-option { display: flex; align-items: flex-start; gap: 10px; padding: 14px 12px; border: 1px solid var(--quiz-line); border-radius: 10px; background: var(--quiz-surface); color: var(--quiz-ink); cursor: pointer; line-height: 1.6; }
.quiz-option input { flex: 0 0 auto; width: 16px; height: 16px; margin: 3px 0 0; accent-color: var(--quiz-accent); }
.quiz-option-letter { flex: 0 0 auto; font-size: 12px; line-height: 22px; color: var(--quiz-muted); }
.quiz-option-copy { min-width: 0; white-space: pre-wrap; }
.quiz-option:hover:has(input:not(:disabled)), .quiz-option.is-selected { border-color: var(--quiz-accent); background: var(--quiz-tint); }
.quiz-option:has(input:focus-visible) { outline: 2px solid var(--quiz-accent); outline-offset: 3px; }
.quiz-option:has(input:disabled) { cursor: default; }
.quiz-option.is-correct { border-color: var(--quiz-accent); background: var(--quiz-tint); }
.quiz-option.is-incorrect { border-color: var(--color-destructive, #dc2626); border-style: dashed; background: var(--quiz-surface); }
.quiz-option-note { display: flex; align-items: center; gap: 5px; margin-top: 10px; font-size: 12px; font-weight: 650; }
.quiz-explanation { display: flex; flex-direction: column; gap: 12px; padding: 18px 0 0; border-top: 1px solid var(--quiz-line); }
.quiz-explanation h4 { font-size: 15px; font-weight: 650; }
.quiz-explanation > p { white-space: pre-wrap; }
.quiz-explanation > button { align-self: flex-start; }
.quiz-footer { padding: 14px 2px 2px; border-top: 1px solid var(--quiz-line); }
.quiz-start { width: 100%; min-height: 42px; }
.quiz-loading { color: var(--quiz-muted); font-size: 12px; }
.quiz-navigation { gap: 10px; }
.quiz-navigation > .quiz-button { padding-inline: 9px; }
.quiz-dialog { width: min(560px, calc(100vw - 32px)); max-width: none; max-height: min(760px, calc(100dvh - 32px)); margin: auto; padding: 0; border: 1px solid var(--quiz-line); border-radius: 16px; color: var(--quiz-ink); background: var(--quiz-surface); box-shadow: 0 20px 70px #13343a33; overflow: hidden; font: inherit; }
.quiz-dialog::backdrop { background: #102b2966; }
.quiz-dialog-frame { display: flex; flex-direction: column; max-height: min(760px, calc(100dvh - 34px)); margin: 0; }
.quiz-dialog-header { flex: 0 0 auto; display: flex; flex-direction: column; height: auto; align-items: stretch; justify-content: flex-start; gap: 12px; padding: 24px 24px 18px; border: 0; }
.quiz-dialog-header h3 { font-size: 20px; line-height: 1.3; letter-spacing: -.4px; }
.quiz-dialog-header p, .quiz-dialog-body > p { color: var(--quiz-muted); font-size: 14px; line-height: 1.6; }
.quiz-dialog-body { display: flex; flex-direction: column; gap: 18px; min-height: 0; padding: 4px 24px 24px; overflow: auto; overscroll-behavior: contain; scrollbar-width: thin; }
.quiz-page-shortcuts { display: flex; flex-wrap: wrap; gap: 10px; }
.quiz-range { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; align-items: end; gap: 12px; min-width: 0; padding: 0; border: 0; }
.quiz-range legend { margin-bottom: 12px; color: var(--quiz-muted); font-size: 12px; }
.quiz-range label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; font-weight: 600; }
.quiz-range input { width: 100%; min-width: 0; min-height: 38px; margin: 0; padding: 6px 10px; border: 1px solid var(--quiz-line); border-radius: 8px; color: var(--quiz-ink); background: var(--quiz-surface); }
.quiz-page-count { display: flex; flex-direction: column; gap: 10px; color: var(--quiz-muted); font-size: 12px; }
.quiz-page-grid { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 10px; min-width: 0; padding: 0; border: 0; }
.quiz-page { position: relative; display: flex; align-items: center; justify-content: center; min-width: 0; min-height: 40px; border: 1px solid var(--quiz-line); border-radius: 8px; background: var(--quiz-surface); font-size: 12px; font-variant-numeric: tabular-nums; cursor: pointer; }
.quiz-page input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: inherit; }
.quiz-page.is-selected { background: var(--quiz-accent); border-color: var(--quiz-accent); color: #fff; }
.quiz-page:has(input:focus-visible) { outline: 2px solid var(--quiz-accent); outline-offset: 3px; }
.quiz-page:has(input:disabled) { opacity: .45; cursor: not-allowed; }
.quiz-page-browse { font-size: 12px; color: var(--quiz-muted); }
.quiz-dialog-footer { flex: 0 0 auto; display: flex; justify-content: flex-end; gap: 12px; padding: 16px 24px; border-top: 1px solid var(--quiz-line); }
.quiz-confirm-dialog { width: min(440px, calc(100vw - 32px)); }
.quiz-sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
@container (max-width: 340px) {
  .quiz-title-row > .quiz-caption { display: none; }
  .quiz-pagination { gap: 3px; }
  .quiz-navigation { flex-wrap: wrap; }
  .quiz-navigation > .quiz-text-button { order: 3; width: 100%; }
  .quiz-option { padding: 12px 10px; gap: 8px; }
}
@media (max-width: 560px) {
  .quiz-dialog-header { padding: 20px 16px 16px; }
  .quiz-dialog-body { padding: 4px 16px 20px; }
  .quiz-dialog-footer { padding: 14px 16px; }
  .quiz-page-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
@media (forced-colors: active) {
  .quiz-page.is-selected, .quiz-index.is-current { outline: 2px solid Highlight; outline-offset: -4px; }
  .quiz-option.is-selected { outline: 2px solid Highlight; }
}
</style>