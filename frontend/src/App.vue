<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  FileText,
  History,
  Languages,
  LibraryBig,
  LogOut,
  Menu,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Trash2,
  Upload,
  Volume2,
  X,
  ZoomIn,
  ZoomOut,
} from "@lucide/vue";
import {
  api,
  type ChatResult,
  type Conversation,
  type DocumentDetail,
  type DocumentSummary,
  type Message,
  type UploadResult,
  type User,
} from "./api";
import CheckMe from "./components/CheckMe.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";

type Tab = "text" | "summary" | "translate" | "study" | "chat";
type MobileSheet = "pages" | "tools" | null;
type DeleteTarget = {
  kind: "document" | "history" | "chat" | "library";
  id?: number;
  title: string;
  message: string;
};
const user = ref<User | null>(null),
  documents = ref<DocumentSummary[]>([]),
  chats = ref<Conversation[]>([]),
  document = ref<DocumentDetail | null>(null);
const messages = ref<Message[]>([]),
  tab = ref<Tab>("text"),
  page = ref(1),
  reading = ref(false),
  sidebar = ref(false),
  navCollapsed = ref(false),
  thumbnailsOpen = ref(true),
  toolsOpen = ref(true),
  language = ref("Luganda");
const mobileSheet = ref<MobileSheet>(null);
const pdfZoom = ref(100),
  toolsWidth = ref(440);
const username = ref(""),
  password = ref(""),
  authMode = ref<"login" | "register">("login"),
  busy = ref(false),
  prompt = ref(""),
  conversationId = ref<number | null>(null);
const summaryPrompt = ref(""),
  summaryResult = ref(""),
  translationResult = ref(""),
  toolBusy = ref(false);
const searchOpen = ref(false),
  searchQuery = ref(""),
  searchInput = ref<HTMLInputElement | null>(null);
const errorToast = ref(""),
  noticeToast = ref(""),
  toastVersion = ref(0),
  toastHost = ref<(HTMLElement & { showPopover: () => void; hidePopover: () => void }) | null>(null),
  messagesViewport = ref<HTMLElement | null>(null),
  deleteTarget = ref<DeleteTarget | null>(null);
const deleting = ref(false), sending = ref(false), navigating = ref(false);
const chatMenu = ref<HTMLDialogElement | null>(null);
const menuChat = ref<Conversation | null>(null);
const menuPosition = ref({ left: '0px', top: '0px' });
let menuTrigger: HTMLElement | null = null;
let errorToastTimer: ReturnType<typeof setTimeout> | undefined;
let noticeToastTimer: ReturnType<typeof setTimeout> | undefined;
let documentRequest = 0;
let sendRequest = 0;
let toolRequest = 0;
let historyRequest = 0;
let overlayTrigger: HTMLElement | null = null;
const currentText = computed(
  () =>
    document.value?.pages.find((item) => item.page_number === page.value)
      ?.text || "No extractable text was found on this page.",
);
const normalizedSearch = computed(() => searchQuery.value.trim().toLowerCase());
const searchedDocuments = computed(() =>
  normalizedSearch.value
    ? documents.value.filter((item) =>
        `${item.title} ${item.filename}`
          .toLowerCase()
          .includes(normalizedSearch.value),
      )
    : documents.value.slice(0, 5),
);
const searchedChats = computed(() =>
  normalizedSearch.value
    ? chats.value.filter((item) =>
        item.title.toLowerCase().includes(normalizedSearch.value),
      )
    : chats.value.slice(0, 5),
);
const searchedPages = computed(() =>
  !normalizedSearch.value || !document.value
    ? []
    : document.value.pages
        .filter((item) =>
          item.text.toLowerCase().includes(normalizedSearch.value),
        )
        .slice(0, 10),
);

async function refreshHistory() {
  const request = ++historyRequest;
  const owner = user.value?.id;
  const [docs, conversations] = await Promise.all([
    api<DocumentSummary[]>("/documents"), api<Conversation[]>("/conversations"),
  ]);
  if (request !== historyRequest || owner !== user.value?.id) return;
  documents.value = docs;
  chats.value = conversations;
}
async function authenticate() {
  if (busy.value) return;
  busy.value = true;
  dismissError();
  try {
    user.value = await api(`/auth/${authMode.value}`, {
      method: "POST",
      body: JSON.stringify({
        username: username.value,
        password: password.value,
      }),
    });
    await refreshHistory();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function logout() {
  if (busy.value || deleting.value) return;
  try {
    await api("/auth/logout", { method: "POST" });
    closeDocument();
    historyRequest++;
    user.value = null;
    documents.value = [];
    chats.value = [];
    closeSearch();
  } catch (e) { showError(e); }
}
function resetPageTools() {
  toolRequest++;
  toolBusy.value = false;
  summaryResult.value = "";
  translationResult.value = "";
}
function invalidateChat() {
  sendRequest++;
  sending.value = false;
  prompt.value = "";
}
function closeDocument() {
  documentRequest++;
  navigating.value = false;
  invalidateChat();
  mobileSheet.value = null;
  speechSynthesis.cancel();
  reading.value = false;
  document.value = null;
  conversationId.value = null;
  messages.value = [];
  resetPageTools();
}
async function openDocument(id: number) {
  const request = ++documentRequest;
  navigating.value = true;
  invalidateChat();
  resetPageTools();
  dismissError();
  try {
    const selected = await api<DocumentDetail>(`/documents/${id}`);
    if (request !== documentRequest) return;
    setDocument(selected);
    tab.value = "text";
    mobileSheet.value = null;
    conversationId.value = null;
    messages.value = [];
    resetPageTools();
    sidebar.value = false;
  } catch (e) {
    if (request === documentRequest) showError(e);
  } finally {
    if (request === documentRequest) navigating.value = false;
  }
}
function setDocument(selected: DocumentDetail) {
  speechSynthesis.cancel();
  reading.value = false;
  document.value = selected;
  page.value = 1;
  pdfZoom.value = 100;
}
function showError(value: unknown) {
  errorToast.value = typeof value === 'string' ? value : value instanceof Error ? value.message : 'Something went wrong. Please try again.';
  toastVersion.value++;
  if (errorToastTimer) clearTimeout(errorToastTimer);
  // Errors remain reachable until dismissed; identical repeated errors still announce.
}
function showNotice(message: string) {
  noticeToast.value = message;
  toastVersion.value++;
  if (noticeToastTimer) clearTimeout(noticeToastTimer);
  noticeToastTimer = setTimeout(() => (noticeToast.value = ""), 5000);
}
async function scrollMessagesToEnd() {
  await nextTick();
  messagesViewport.value?.scrollTo({
    top: messagesViewport.value.scrollHeight,
    behavior: "smooth",
  });
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file) return;
  if (busy.value || deleting.value) return;
  const context = documentRequest;
  busy.value = true;
  dismissError();
  try {
    const data = new FormData();
    data.append("file", file);
    const created = await api<UploadResult>("/documents", {
      method: "POST",
      body: data,
    });
    await refreshHistory();
    if (context === documentRequest) await openDocument(created.id);
    if (created.existing)
      showNotice(
        "This PDF is already in your library, so the existing copy was opened.",
      );
    input.value = "";
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
async function openChat(id: number) {
  const request = ++documentRequest;
  navigating.value = true;
  invalidateChat();
  resetPageTools();
  try {
    const history = chats.value.find((item) => item.id === id);
    if (!history?.document_id) throw new Error('This conversation has no source PDF. You can delete it from its chat menu.');
    const [result, selected] = await Promise.all([
      api<{ id: number; title: string; messages: Message[] }>(`/conversations/${id}`),
      api<DocumentDetail>(`/documents/${history.document_id}`),
    ]);
    if (request !== documentRequest) return;
    setDocument(selected);
    conversationId.value = id;
    messages.value = result.messages;
    tab.value = "chat";
    toolsOpen.value = true;
    sidebar.value = false;
    if (innerWidth <= 676) await openMobileSheet('tools');
    await scrollMessagesToEnd();
  } catch (e) {
    if (request === documentRequest) showError(e);
  } finally {
    if (request === documentRequest) navigating.value = false;
  }
}
async function send() {
  if (!prompt.value.trim() || sending.value || navigating.value || deleting.value || !document.value) return;
  const request = ++sendRequest;
  const context = documentRequest;
  const documentId = document.value.id;
  const chatId = conversationId.value;
  const content = prompt.value;
  const optimisticMessage: Message = { role: "user", content };
  messages.value.push(optimisticMessage);
  prompt.value = "";
  void scrollMessagesToEnd();
  sending.value = true;
  try {
    const result = await api<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({
        content,
        document_id: documentId,
        conversation_id: chatId,
      }),
    });
    if (request !== sendRequest || context !== documentRequest || document.value?.id !== documentId) return;
    conversationId.value = result.conversation_id;
    messages.value.push({ role: "assistant", content: result.reply });
    await refreshHistory();
    if (request === sendRequest && context === documentRequest) await scrollMessagesToEnd();
  } catch (e) {
    if (request !== sendRequest || context !== documentRequest) return;
    const lastMessage = messages.value[messages.value.length - 1];
    if (lastMessage?.role === 'user' && lastMessage.content === content) {
      messages.value.pop();
      if (!prompt.value) prompt.value = content;
    }
    showError(e);
  } finally {
    if (request === sendRequest) sending.value = false;
  }
}
function sendOnEnter(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void send();
  }
}
async function pageRequest(
  content: string,
  operation: "summary" | "translation",
) {
  if (!document.value) throw new Error("Open a document first");
  const result = await api<ChatResult>("/chat", {
    method: "POST",
    body: JSON.stringify({
      content,
      operation,
      document_id: document.value.id,
      page_number: page.value,
    }),
  });
  return result.reply;
}
async function summarizePage() {
  if (toolBusy.value || navigating.value || !document.value) return;
  const request = ++toolRequest;
  toolBusy.value = true;
  dismissError();
  try {
    const result = await pageRequest(
      `Summarize only this page${summaryPrompt.value.trim() ? ` with this focus: ${summaryPrompt.value.trim()}` : ""}. Give a concise heading and 3 to 5 key points.`,
      "summary",
    );
    if (request === toolRequest) summaryResult.value = result;
  } catch (e) {
    if (request === toolRequest) showError(e);
  } finally {
    if (request === toolRequest) toolBusy.value = false;
  }
}
async function translatePage() {
  if (toolBusy.value || navigating.value || !document.value) return;
  const request = ++toolRequest;
  toolBusy.value = true;
  dismissError();
  try {
    const result = await pageRequest(
      `Translate only this page into ${language.value}. Preserve meaning and formatting. Return only the translation.`,
      "translation",
    );
    if (request === toolRequest) translationResult.value = result;
  } catch (e) {
    if (request === toolRequest) showError(e);
  } finally {
    if (request === toolRequest) toolBusy.value = false;
  }
}
async function startStudy() {
  tab.value = "study";
  toolsOpen.value = true;
  if (innerWidth <= 676) await openMobileSheet("tools");
}
function requestDeleteHistory() {
  deleteTarget.value = {
    kind: "history",
    title: "Clear chat history?",
    message: "This permanently removes all saved conversations.",
  };
}
function requestClearLibrary() {
  deleteTarget.value = {
    kind: 'library', title: 'Clear your library?',
    message: 'All PDFs and their related conversations will be permanently removed. This cannot be undone.',
  };
}
async function openChatMenu(chat: Conversation, event: MouseEvent | KeyboardEvent) {
  event.preventDefault();
  const trigger = event.currentTarget as HTMLElement;
  menuTrigger = trigger.querySelector<HTMLElement>('.chat-menu-trigger') ?? trigger;
  const rect = trigger.getBoundingClientRect();
  const pointer = event instanceof MouseEvent && event.type === 'contextmenu' && (event.clientX !== 0 || event.clientY !== 0);
  const x = pointer ? event.clientX : rect.right;
  const y = pointer ? event.clientY : rect.bottom;
  menuChat.value = chat;
  await nextTick();
  const dialog = chatMenu.value;
  if (!dialog) return;
  if (!dialog.open) dialog.showModal();
  menuPosition.value = {
    left: `${Math.max(10, Math.min(x, innerWidth - dialog.offsetWidth - 10))}px`,
    top: `${Math.max(10, Math.min(y, innerHeight - dialog.offsetHeight - 10))}px`,
  };
  dialog.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
}
function closeChatMenu() {
  if (!chatMenu.value?.open) return;
  chatMenu.value?.close();
  menuChat.value = null;
  if (menuTrigger?.isConnected) menuTrigger.focus({ preventScroll: true });
}
function menuOutside(event: MouseEvent) {
  const dialog = chatMenu.value;
  if (!dialog || event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeChatMenu();
}
function menuKeydown(event: KeyboardEvent) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End', 'Tab'].includes(event.key)) return;
  event.preventDefault();
  const items = Array.from(chatMenu.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
  const current = items.indexOf(globalThis.document.activeElement as HTMLButtonElement);
  const offset = event.key === 'ArrowUp' || (event.key === 'Tab' && event.shiftKey) ? -1 : 1;
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (current + offset + items.length) % items.length;
  items[index]?.focus();
}
function openMenuConversation() {
  const id = menuChat.value?.id;
  closeChatMenu();
  if (id !== undefined) void openChat(id);
}
function deleteMenuConversation() {
  const chat = menuChat.value;
  closeChatMenu();
  if (chat) deleteTarget.value = {
    kind: 'chat', id: chat.id, title: 'Delete this chat?',
    message: `“${chat.title}” will be permanently removed. Your PDF will stay in your library.`,
  };
}
function requestDeleteDocument(item: DocumentSummary) {
  deleteTarget.value = {
    kind: "document",
    id: item.id,
    title: "Delete this PDF?",
    message: `${item.title} and its related chat history will be permanently removed.`,
  };
}
async function confirmDelete() {
  const target = deleteTarget.value;
  if (!target || deleting.value) return;
  deleting.value = true;
  dismissError();
  try {
    const route = target.kind === 'history' ? '/conversations' : target.kind === 'chat' ? `/conversations/${target.id}` : target.kind === 'library' ? '/documents' : `/documents/${target.id}`;
    await api(route, { method: 'DELETE' });
    if (target.kind === "history" || (target.kind === 'chat' && conversationId.value === target.id)) {
      documentRequest++;
      navigating.value = false;
      invalidateChat();
      conversationId.value = null;
      messages.value = [];
    } else if (target.kind === 'library' || (target.kind === 'document' && document.value?.id === target.id)) closeDocument();
    // Reflect the successful deletion even if refreshing the lists subsequently fails.
    if (target.kind === 'library') { documents.value = []; chats.value = []; }
    if (target.kind === 'history') chats.value = [];
    if (target.kind === 'chat') chats.value = chats.value.filter(chat => chat.id !== target.id);
    if (target.kind === 'document') {
      documents.value = documents.value.filter(doc => doc.id !== target.id);
      chats.value = chats.value.filter(chat => chat.document_id !== target.id);
    }
    showNotice(target.kind === 'history' ? 'Chat history cleared.' : target.kind === 'chat' ? 'Chat deleted.' : target.kind === 'library' ? 'Library cleared.' : 'PDF deleted.');
    deleteTarget.value = null;
    await refreshHistory();
  } catch (e) {
    // Native modal dialogs consume pointer events. Close it so the floating toast stays actionable.
    deleteTarget.value = null;
    showError(e);
  } finally {
    deleting.value = false;
  }
}
function speak() {
  if (reading.value) {
    speechSynthesis.cancel();
    reading.value = false;
    return;
  }
  const utterance = new SpeechSynthesisUtterance(currentText.value);
  utterance.onend = () => {
    reading.value = false;
    if (document.value && page.value < document.value.page_count) {
      page.value++;
      speak();
    }
  };
  reading.value = true;
  speechSynthesis.speak(utterance);
}
function selectPage(nextPage: number) {
  page.value = nextPage;
  closeMobileSheet();
  resetPageTools();
}
function move(by: number) {
  if (document.value)
    selectPage(
      Math.min(document.value.page_count, Math.max(1, page.value + by)),
    );
}
function changeZoom(by: number) {
  pdfZoom.value = Math.min(160, Math.max(75, pdfZoom.value + by));
}
function toggleNavigation() {
  navCollapsed.value = !navCollapsed.value;
  if (navCollapsed.value) toolsOpen.value = true;
}
async function openMobileSheet(nextSheet: Exclude<MobileSheet, null>) {
  overlayTrigger = globalThis.document.activeElement as HTMLElement;
  mobileSheet.value = nextSheet;
  await nextTick();
  globalThis.document
    .querySelector<HTMLElement>('[role="dialog"] button')
    ?.focus();
}
function closeMobileSheet() {
  const trigger = overlayTrigger;
  mobileSheet.value = null;
  nextTick(() => trigger?.focus());
}
function openMobileTools(nextTab: Tab = tab.value) {
  tab.value = nextTab;
  toolsOpen.value = true;
  void openMobileSheet("tools");
}
function closeTools() {
  closeMobileSheet();
  toolsOpen.value = false;
}
async function openNavigation() {
  overlayTrigger = globalThis.document.activeElement as HTMLElement;
  sidebar.value = true;
  await nextTick();
  globalThis.document.querySelector<HTMLElement>(".sidebar .close")?.focus();
}
function closeNavigation() {
  sidebar.value = false;
  nextTick(() => overlayTrigger?.focus());
}
function closeOverlaysOnEscape(event: KeyboardEvent) {
  if (globalThis.document.querySelector('dialog[open]')) return;
  if (event.key !== "Escape") return;
  if (mobileSheet.value) closeMobileSheet();
  if (sidebar.value) closeNavigation();
}
async function showSearch() {
  searchOpen.value = true;
  await nextTick();
  searchInput.value?.focus();
}
function closeSearch() {
  searchOpen.value = false;
  searchQuery.value = "";
}
async function openSearchDocument(id: number) {
  await openDocument(id);
  closeSearch();
}
function openSearchPage(pageNumber: number) {
  selectPage(pageNumber);
  closeSearch();
}
function resizePane(pane: "nav" | "tools", event: PointerEvent) {
  if (innerWidth <= 900) return;
  const root = globalThis.document.documentElement;
  const startX = event.clientX;
  const property = pane === "nav" ? "--nav-width" : "--tools-width";
  const current =
    pane === "tools"
      ? toolsWidth.value
      : Number.parseFloat(getComputedStyle(root).getPropertyValue(property));
  const minimum = pane === "nav" ? 190 : 300;
  const maximum = pane === "nav" ? 360 : 600;
  if (pane === "nav") navCollapsed.value = false;
  const movePointer = (moveEvent: PointerEvent) => {
    const delta =
      pane === "nav" ? moveEvent.clientX - startX : startX - moveEvent.clientX;
    const width = Math.min(maximum, Math.max(minimum, current + delta));
    if (pane === "tools") toolsWidth.value = width;
    else root.style.setProperty(property, `${width}px`);
  };
  const stopPointer = () => {
    removeEventListener("pointermove", movePointer);
    removeEventListener("pointerup", stopPointer);
  };
  addEventListener("pointermove", movePointer);
  addEventListener("pointerup", stopPointer, { once: true });
}
function resizePaneByKey(pane: "nav" | "tools", direction: number) {
  const root = globalThis.document.documentElement,
    property = pane === "nav" ? "--nav-width" : "--tools-width";
  const current =
    pane === "tools"
      ? toolsWidth.value
      : Number.parseFloat(getComputedStyle(root).getPropertyValue(property));
  const width = Math.min(
    pane === "nav" ? 360 : 600,
    Math.max(pane === "nav" ? 190 : 300, current + direction * 16),
  );
  if (pane === "tools") toolsWidth.value = width;
  else root.style.setProperty(property, `${width}px`);
}
function formatDocumentDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}
function dismissError() {
  errorToast.value = "";
  if (errorToastTimer) clearTimeout(errorToastTimer);
}
function dismissNotice() {
  noticeToast.value = '';
  if (noticeToastTimer) clearTimeout(noticeToastTimer);
}
watch([errorToast, noticeToast, toastVersion], async () => {
  await nextTick();
  const host = toastHost.value;
  if (!host) return;
  // Manual popovers stay above native modal dialogs without stealing focus.
  if (errorToast.value || noticeToast.value) {
    if (host.matches(':popover-open')) host.hidePopover();
    host.showPopover();
  } else if (host.matches(':popover-open')) host.hidePopover();
});
watch(language, resetPageTools);
onMounted(async () => {
  globalThis.document.addEventListener("keydown", closeOverlaysOnEscape);
  addEventListener('resize', closeChatMenu);
  try {
    user.value = await api("/auth/me");
  } catch {
    user.value = null;
  }
  if (user.value) {
    try { await refreshHistory(); } catch (e) { showError(e); }
  }
});
onBeforeUnmount(() => {
  globalThis.document.removeEventListener("keydown", closeOverlaysOnEscape);
  removeEventListener('resize', closeChatMenu);
  documentRequest++;
  historyRequest++;
  invalidateChat();
  resetPageTools();
  dismissError();
  dismissNotice();
});
</script>

<template>
  <div class="app-root">
    <div ref="toastHost" class="toast-stack" popover="manual">
    <Transition name="toast" mode="out-in"
      ><aside
        v-if="errorToast"
        :key="toastVersion"
        class="error-toast"
        role="alert"
        aria-live="assertive"
      >
        <AlertCircle :size="20" />
        <div>
          <strong>Something went wrong</strong>
          <p>{{ errorToast }}</p>
        </div>
        <button aria-label="Dismiss error" @click="dismissError">
          <X :size="17" />
        </button></aside
    ></Transition>
    <Transition name="toast"
      ><aside
        v-if="noticeToast"
        class="notice-toast"
        role="status"
        aria-live="polite"
      >
        <BookOpen :size="20" />
        <p>{{ noticeToast }}</p>
        <button aria-label="Dismiss notification" @click="dismissNotice"><X :size="17" /></button>
      </aside></Transition
    >
    </div>
    <section v-if="!user" class="auth-page">
      <form class="auth-box" @submit.prevent="authenticate">
        <div class="auth-brand">
          <b><BookOpen :size="22" /></b> edutool
        </div>
        <p class="eyebrow">YOUR STUDY WORKSPACE</p>
        <h1>
          {{ authMode === "login" ? "Welcome back" : "Create your account" }}
        </h1>
        <label
          >Username<input
            v-model="username"
            required
            minlength="3"
            autocomplete="username" /></label
        ><label
          >Password<input
            v-model="password"
            required
            minlength="8"
            type="password"
            autocomplete="current-password"
        /></label>
        <button class="button primary auth-submit" :disabled="busy">
          {{
            busy
              ? "Please wait…"
              : authMode === "login"
                ? "Sign in"
                : "Register"
          }}</button
        ><button
          type="button"
          class="auth-switch"
          @click="authMode = authMode === 'login' ? 'register' : 'login'"
        >
          {{
            authMode === "login"
              ? "New here? Create an account"
              : "Already registered? Sign in"
          }}
        </button>
      </form>
    </section>
    <div
      v-else
      class="shell"
      :class="{ 'nav-collapsed': navCollapsed, 'document-open': document }"
    >
      <aside
        class="sidebar"
        :class="{ open: sidebar }"
        aria-label="Document library"
        @keydown.esc="closeNavigation"
      >
        <div class="brand">
          <b><BookOpen :size="20" /></b><span>edutool</span
          ><button
            class="close"
            aria-label="Close navigation"
            @click="closeNavigation"
          >
            <X :size="19" />
          </button>
        </div>
        <label class="upload-button"
          ><Upload :size="17" /><span>{{
            busy ? "Processing…" : "Upload PDF"
          }}</span
          ><input
            type="file"
            accept="application/pdf"
            :disabled="busy"
            @change="upload"
        /></label>
        <nav>
          <p class="nav-title">
            <LibraryBig :size="14" /><span>RECENT DOCUMENTS</span>
          </p>
          <button
            v-for="item in documents.slice(0, 5)"
            :key="item.id"
            :title="item.title"
            :class="{ active: item.id === document?.id }"
            :aria-current="item.id === document?.id ? 'page' : undefined"
            @click="openDocument(item.id)"
          >
            <FileText :size="17" /><span
              >{{ item.title }}<small>{{ item.page_count }} pages</small></span
            >
          </button>
          <p v-if="!documents.length" class="empty-nav">
            Upload your first PDF
          </p>
          <div class="nav-title history-title">
            <History :size="14" /><span>CHAT HISTORY</span>
            <button
              v-if="chats.length"
              class="history-clear"
              title="Clear chat history"
              aria-label="Clear chat history"
              @click="requestDeleteHistory"
            >
              <Trash2 :size="14" />
            </button>
          </div>
          <div
            v-for="chat in chats"
            :key="chat.id"
            class="chat-history-row"
            @contextmenu="openChatMenu(chat, $event)"
            @keydown.shift.f10="openChatMenu(chat, $event)"
          >
            <button :title="chat.title" :class="{ active: conversationId === chat.id }" @click="openChat(chat.id)">
              <MessageSquare :size="17" /><span>{{ chat.title }}</span>
            </button>
            <button class="chat-menu-trigger" :aria-label="`Options for ${chat.title}`" aria-haspopup="menu"
              :aria-expanded="menuChat?.id === chat.id" aria-controls="saved-chat-menu" @click="openChatMenu(chat, $event)">
              <MoreHorizontal :size="18" />
            </button>
          </div>
          <p v-if="!chats.length" class="empty-nav">No conversations yet</p>
        </nav>
        <nav class="bottom">
          <button title="Sign out" @click="logout">
            <LogOut :size="17" /><span>Sign out</span>
          </button>
          <div class="profile">
            <i>{{ user.username.slice(0, 2).toUpperCase() }}</i
            ><span
              ><strong>{{ user.username }}</strong
              ><small>Student workspace</small></span
            >
          </div>
        </nav>
        <div
          class="pane-resizer nav-resizer"
          role="separator"
          aria-label="Resize navigation"
          tabindex="0"
          @pointerdown="resizePane('nav', $event)"
          @keydown.left.prevent="resizePaneByKey('nav', -1)"
          @keydown.right.prevent="resizePaneByKey('nav', 1)"
        ></div>
      </aside>
      <button
        v-if="sidebar"
        class="nav-scrim"
        aria-label="Close navigation"
        @click="closeNavigation"
      ></button>
      <main :inert="sidebar ? true : undefined">
        <header :inert="mobileSheet ? true : undefined">
          <button
            class="menu"
            aria-label="Open navigation"
            @click="openNavigation"
          >
            <Menu :size="20" /></button
          ><button
            class="nav-collapse"
            :aria-label="
              navCollapsed ? 'Expand navigation' : 'Collapse navigation'
            "
            :aria-pressed="navCollapsed"
            @click="toggleNavigation"
          >
            <PanelLeftOpen v-if="navCollapsed" :size="19" /><PanelLeftClose
              v-else
              :size="19"
            /></button
          ><button
            class="crumb"
            :aria-label="document ? 'Back to My library' : undefined"
            :disabled="!document"
            @click="document && closeDocument()"
          >
            <span class="crumb-library">My library</span
            ><ChevronRight :size="14" /><span class="crumb-document">{{
              document?.title || "Choose a document"
            }}</span></button
          ><button class="search" @click="showSearch">
            <Search :size="16" /> Search workspace
          </button>
        </header>
        <div
          v-if="searchOpen"
          class="search-scrim"
          @click.self="closeSearch"
          @keydown.esc="closeSearch"
        >
          <section
            class="search-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Search workspace"
          >
            <div class="search-field">
              <Search :size="18" /><input
                ref="searchInput"
                v-model="searchQuery"
                aria-label="Search documents, chats, and page text"
                placeholder="Search documents, chats, and this PDF…"
              /><button aria-label="Close search" @click="closeSearch">
                <X :size="18" />
              </button>
            </div>
            <div class="search-results">
              <div v-if="searchedDocuments.length">
                <p class="search-group">DOCUMENTS</p>
                <button
                  v-for="item in searchedDocuments"
                  :key="`document-${item.id}`"
                  @click="openSearchDocument(item.id)"
                >
                  <FileText :size="17" /><span
                    ><strong>{{ item.title }}</strong
                    ><small
                      >{{ item.page_count }} pages · {{ item.filename }}</small
                    ></span
                  >
                </button>
              </div>
              <div v-if="searchedPages.length">
                <p class="search-group">PAGES IN {{ document?.title }}</p>
                <button
                  v-for="item in searchedPages"
                  :key="`page-${item.page_number}`"
                  @click="openSearchPage(item.page_number)"
                >
                  <BookOpen :size="17" /><span
                    ><strong>Page {{ item.page_number }}</strong
                    ><small
                      >{{ item.text.slice(0, 90)
                      }}{{ item.text.length > 90 ? "…" : "" }}</small
                    ></span
                  >
                </button>
              </div>
              <div v-if="searchedChats.length">
                <p class="search-group">CONVERSATIONS</p>
                <button
                  v-for="item in searchedChats"
                  :key="`chat-${item.id}`"
                  @click="
                    openChat(item.id);
                    closeSearch();
                  "
                >
                  <MessageSquare :size="17" /><span
                    ><strong>{{ item.title }}</strong
                    ><small>Open conversation</small></span
                  >
                </button>
              </div>
              <p
                v-if="
                  !searchedDocuments.length &&
                  !searchedPages.length &&
                  !searchedChats.length
                "
                class="search-empty"
              >
                No results for “{{ searchQuery }}”
              </p>
            </div>
          </section>
        </div>
        <section
          v-if="!document"
          class="library-view"
          aria-labelledby="library-title"
        >
          <div class="library-heading">
            <div>
              <p class="eyebrow">YOUR COLLECTION</p>
              <h1 id="library-title">My library</h1>
              <p>
                {{ documents.length }}
                {{ documents.length === 1 ? "document" : "documents" }} ready to
                read
              </p>
            </div>
            <div class="library-actions">
            <button v-if="documents.length" class="button library-clear" :disabled="busy || deleting" @click="requestClearLibrary">
              <Trash2 :size="16" /> Clear library
            </button>
            <label
              class="button primary library-upload"
              :aria-busy="busy"
              :aria-disabled="busy"
              ><Upload :size="17" aria-hidden="true" />
              {{ documents.length ? "Upload PDF" : "Upload your first PDF"
              }}<span
                class="library-upload-status"
                role="status"
                aria-live="polite"
                >{{
                  busy
                    ? "Uploading PDF. Upload is temporarily unavailable."
                    : ""
                }}</span
              ><input
                type="file"
                accept="application/pdf"
                :disabled="busy"
                @change="upload"
            /></label>
            </div>
          </div>
          <div v-if="documents.length" class="library-list">
            <div class="library-columns" aria-hidden="true">
              <span>Document</span><span>Pages</span><span>Added</span
              ><span></span><span>Actions</span>
            </div>
            <ul>
              <li v-for="item in documents" :key="item.id" class="library-item">
                <button class="library-row" @click="openDocument(item.id)">
                  <span class="library-file-icon"
                    ><FileText :size="20" aria-hidden="true" /></span
                  ><span class="library-document"
                    ><strong>{{ item.title }}</strong
                    ><small>{{ item.filename }}</small></span
                  ><span class="library-pages">{{ item.page_count }} pages</span
                  ><span class="library-date">{{
                    formatDocumentDate(item.created_at)
                  }}</span
                  ><ChevronRight
                    class="library-chevron"
                    :size="18"
                    aria-hidden="true"
                  />
                </button>
                <button
                  class="library-delete"
                  :aria-label="`Delete ${item.title}`"
                  title="Delete PDF"
                  @click="requestDeleteDocument(item)"
                >
                  <Trash2 :size="17" /><span>Delete</span>
                </button>
              </li>
            </ul>
          </div>
          <div v-else class="library-empty">
            <LibraryBig :size="32" aria-hidden="true" />
            <h2>No PDFs yet</h2>
            <p>Upload a PDF to start reading and studying.</p>
          </div>
        </section>
        <template v-else
          ><section class="title">
            <div>
              <p class="eyebrow"><FileText :size="14" /> PDF DOCUMENT</p>
              <h1>{{ document.title }}</h1>
              <small
                >{{ document.page_count }} pages · Page {{ page }} open</small
              >
            </div>
            <div class="document-actions">
              <button class="button ghost" @click="closeDocument">
                <ArrowLeft :size="16" /> Library</button
              ><label class="button secondary"
                ><Plus :size="16" /> New PDF<input
                  class="hidden-input"
                  type="file"
                  accept="application/pdf"
                  @change="upload" /></label
              ><button
                class="button study-button"
                :disabled="toolBusy"
                @click="startStudy"
              >
                <BrainCircuit :size="16" /> Check Me</button
              ><button class="button primary" @click="speak">
                <Volume2 :size="16" /> {{ reading ? "Stop" : "Listen" }}
              </button>
            </div>
          </section>
          <section
            class="reader"
            :class="{
              'tools-closed': !toolsOpen,
              'mobile-tools-open': mobileSheet === 'tools',
            }"
            :style="
              toolsOpen
                ? { 'grid-template-columns': `minmax(0, 1fr) ${toolsWidth}px` }
                : undefined
            "
          >
            <section
              class="reader-main"
              :inert="mobileSheet ? true : undefined"
            >
              <div class="reader-bar">
                <button
                  class="reader-control"
                  :aria-pressed="thumbnailsOpen"
                  @click="thumbnailsOpen = !thumbnailsOpen"
                >
                  <LibraryBig :size="16" /> Pages
                  <span>{{ document.page_count }}</span>
                </button>
                <div class="page-status">
                  <span class="page-count"
                    >Page {{ page }} of {{ document.page_count }}</span
                  >
                  <div class="zoom-controls" aria-label="PDF zoom controls">
                    <button
                      aria-label="Zoom out"
                      :disabled="pdfZoom === 75"
                      @click="changeZoom(-10)"
                    >
                      <ZoomOut :size="16" /></button
                    ><button
                      class="zoom-value"
                      aria-label="Reset zoom"
                      title="Reset zoom"
                      @click="pdfZoom = 100"
                    >
                      {{ pdfZoom }}%</button
                    ><button
                      aria-label="Zoom in"
                      :disabled="pdfZoom === 160"
                      @click="changeZoom(10)"
                    >
                      <ZoomIn :size="16" /></button
                    ><button
                      aria-label="Reset zoom"
                      title="Reset zoom"
                      @click="pdfZoom = 100"
                    >
                      <RotateCcw :size="15" />
                    </button>
                  </div>
                </div>
                <button
                  class="reader-control tools-toggle"
                  :aria-pressed="toolsOpen"
                  @click="toolsOpen = !toolsOpen"
                >
                  <PanelRightClose v-if="toolsOpen" :size="17" /><PanelRightOpen
                    v-else
                    :size="17"
                  />
                  {{ toolsOpen ? "Hide tools" : "Show tools" }}
                </button>
              </div>
              <aside
                v-if="thumbnailsOpen"
                class="rail"
                aria-label="Document pages"
              >
                <button
                  v-for="item in document.pages"
                  :key="item.page_number"
                  :aria-label="`Open page ${item.page_number}`"
                  :class="{ selected: item.page_number === page }"
                  @click="selectPage(item.page_number)"
                >
                  <span></span><b>{{ item.page_number }}</b>
                </button>
              </aside>
              <section class="pdf">
                <article :style="{ '--pdf-zoom': pdfZoom / 100 }">
                  <p class="chapter">{{ document.title }}</p>
                  <h2>Page {{ page }}</h2>
                  <hr />
                  <p class="document-text">{{ currentText }}</p>
                  <footer>
                    {{ document.filename }} <span>{{ page }}</span>
                  </footer>
                </article>
              </section>
              <div class="paginate">
                <button
                  class="button secondary"
                  :disabled="page === 1"
                  @click="move(-1)"
                >
                  <ChevronLeft :size="16" /> Previous</button
                ><span>{{ page }} / {{ document.page_count }}</span
                ><button
                  class="button secondary"
                  :disabled="page === document.page_count"
                  @click="move(1)"
                >
                  Next <ChevronRight :size="16" />
                </button>
              </div>
            </section>
            <section
              v-show="toolsOpen"
              class="tools"
              aria-label="Study tools"
              :role="mobileSheet === 'tools' ? 'dialog' : undefined"
              :aria-modal="mobileSheet === 'tools' ? true : undefined"
              :aria-labelledby="
                mobileSheet === 'tools' ? 'tools-sheet-title' : undefined
              "
              @keydown.esc="closeTools"
            >
              <div class="mobile-sheet-handle" aria-hidden="true"></div>
              <div
                class="pane-resizer tools-resizer"
                role="separator"
                aria-label="Resize study tools"
                tabindex="0"
                @pointerdown="resizePane('tools', $event)"
                @keydown.left.prevent="resizePaneByKey('tools', -1)"
                @keydown.right.prevent="resizePaneByKey('tools', 1)"
              ></div>
              <div class="tools-header">
                <div>
                  <p class="eyebrow">PAGE {{ page }}</p>
                  <strong id="tools-sheet-title">Study tools</strong>
                </div>
                <div class="tools-width-controls">
                  <button
                    aria-label="Narrower study tools"
                    :disabled="toolsWidth <= 300"
                    @click="resizePaneByKey('tools', -1)"
                  >
                    <ChevronRight :size="16" /></button
                  ><span>{{ toolsWidth }}px</span
                  ><button
                    aria-label="Wider study tools"
                    :disabled="toolsWidth >= 600"
                    @click="resizePaneByKey('tools', 1)"
                  >
                    <ChevronLeft :size="16" /></button
                  ><button aria-label="Close study tools" @click="closeTools">
                    <X :size="18" />
                  </button>
                </div>
              </div>
              <div class="tabs">
                <button
                  :class="{ selected: tab === 'text' }"
                  @click="tab = 'text'"
                >
                  Text</button
                ><button
                  :class="{ selected: tab === 'summary' }"
                  @click="tab = 'summary'"
                >
                  <Sparkles :size="14" /> Summary</button
                ><button
                  :class="{ selected: tab === 'translate' }"
                  @click="tab = 'translate'"
                >
                  <Languages :size="14" /> Translate</button
                ><button
                  :class="{ selected: tab === 'study' }"
                  @click="tab = 'study'"
                >
                  <BrainCircuit :size="14" /> Check Me</button
                ><button
                  :class="{ selected: tab === 'chat' }"
                  @click="tab = 'chat'"
                >
                  <MessageSquare :size="14" /> Chat
                </button>
              </div>
              <div class="content" v-show="tab === 'text'">
                <div class="head">
                  <div>
                    <p class="eyebrow">PAGE {{ page }}</p>
                    <h2>Extracted text</h2>
                  </div>
                  <button
                    class="play"
                    aria-label="Read this page"
                    @click="speak"
                  >
                    <Pause v-if="reading" :size="17" /><Play
                      v-else
                      :size="17"
                    />
                  </button>
                </div>
                <p class="body">{{ currentText }}</p>
                <div class="tts">
                  <Volume2 :size="19" /><span
                    ><strong>{{
                      reading ? "Reading this document" : "Listen to this page"
                    }}</strong
                    ><small>Continues page by page automatically</small></span
                  >
                </div>
              </div>
              <div class="content summary-tool" v-show="tab === 'summary'">
                <div class="tool-identity summary-identity">
                  <Sparkles :size="20" />
                  <div>
                    <p class="eyebrow">PAGE {{ page }} ONLY</p>
                    <h2>Focused summary</h2>
                  </div>
                </div>
                <p class="body">
                  Create a concise summary using only the page currently open on
                  the left.
                </p>
                <label for="summary-focus">Optional focus</label
                ><textarea
                  id="summary-focus"
                  v-model="summaryPrompt"
                  placeholder="Example: Focus on the importance of database systems"
                ></textarea
                ><button
                  class="button summary-action"
                  :disabled="toolBusy || navigating"
                  @click="summarizePage"
                >
                  {{ toolBusy ? "Summarizing…" : "Summarize open page" }}
                </button>
                <div v-if="summaryResult" class="tool-result summary-result">
                  <p class="result-label">PAGE {{ page }} SUMMARY</p>
                  <p>{{ summaryResult }}</p>
                </div>
              </div>
              <div
                class="content translate-tool"
                v-show="tab === 'translate'"
              >
                <div class="tool-identity translate-identity">
                  <Languages :size="20" />
                  <div>
                    <p class="eyebrow">PAGE {{ page }} ONLY</p>
                    <h2>Page translator</h2>
                  </div>
                </div>
                <p class="body">
                  Translate the open page without changing the original
                  document.
                </p>
                <label for="translation-language">Target language</label
                ><select id="translation-language" v-model="language">
                  <option>Luganda</option>
                  <option>Arabic</option>
                  <option>French</option>
                  <option>Swahili</option></select
                ><button
                  class="button translate-action"
                  :disabled="toolBusy || navigating"
                  @click="translatePage"
                >
                  {{ toolBusy ? "Translating…" : `Translate to ${language}` }}
                </button>
                <div
                  v-if="translationResult"
                  class="tool-result translation-result"
                >
                  <p class="result-label">{{ language.toUpperCase() }}</p>
                  <p :dir="language === 'Arabic' ? 'rtl' : 'ltr'">
                    {{ translationResult }}
                  </p>
                </div>
              </div>
              <div class="content study-tool" v-show="tab === 'study'">
                <CheckMe
                  :key="document.id"
                  :document-id="document.id"
                  :page-count="document.page_count"
                  :current-page="page"
                  @open-page="selectPage"
                  @error="showError"
                />
              </div>
              <div class="content chat-content" v-show="tab === 'chat'">
                <div class="head">
                  <div>
                    <p class="eyebrow">DOCUMENT CHAT</p>
                    <h2>Ask your material</h2>
                  </div>
                  <MessageSquare :size="20" />
                </div>
                <div ref="messagesViewport" class="messages">
                  <p v-if="!messages.length" class="chat-empty">
                    Ask a question. Answers are grounded in this document.
                  </p>
                  <div
                    v-for="(message, index) in messages"
                    :key="index"
                    :class="['message', message.role]"
                  >
                    {{ message.content }}
                  </div>
                </div>
                <form class="composer" @submit.prevent="send">
                  <textarea
                    v-model="prompt"
                    aria-label="Message about this document"
                    placeholder="Ask about this document…"
                    @keydown="sendOnEnter"
                  ></textarea
                  ><button
                    class="play"
                    :disabled="sending || navigating || deleting || !prompt.trim()"
                    aria-label="Send message"
                  >
                    <Send :size="18" />
                  </button>
                </form>
              </div>
            </section>
            <nav
              class="mobile-reader-dock"
              :inert="mobileSheet ? true : undefined"
              aria-label="Reader controls"
            >
              <button
                :disabled="page === 1"
                aria-label="Previous page"
                @click="move(-1)"
              >
                <ChevronLeft :size="20" /><span>Previous</span></button
              ><button
                aria-label="Choose page"
                @click="openMobileSheet('pages')"
              >
                <LibraryBig :size="19" /><span
                  >{{ page }} / {{ document.page_count }}</span
                ></button
              ><button
                :aria-label="reading ? 'Stop reading' : 'Listen to page'"
                :aria-pressed="reading"
                @click="speak"
              >
                <Pause v-if="reading" :size="20" /><Volume2
                  v-else
                  :size="20"
                /><span>{{ reading ? "Stop" : "Listen" }}</span></button
              ><button aria-label="Open study tools" @click="openMobileTools()">
                <Sparkles :size="20" /><span>Tools</span></button
              ><button
                :disabled="page === document.page_count"
                aria-label="Next page"
                @click="move(1)"
              >
                <ChevronRight :size="20" /><span>Next</span>
              </button>
            </nav>
            <button
              v-if="mobileSheet"
              class="sheet-scrim"
              aria-label="Close panel"
              tabindex="-1"
              @click="closeMobileSheet"
            ></button>
            <section
              v-if="mobileSheet === 'pages'"
              class="mobile-sheet page-sheet"
              role="dialog"
              aria-modal="true"
              aria-labelledby="page-sheet-title"
              @keydown.esc="closeMobileSheet"
            >
              <div class="mobile-sheet-handle" aria-hidden="true"></div>
              <div class="mobile-sheet-header">
                <div>
                  <p class="eyebrow">{{ document.title }}</p>
                  <strong id="page-sheet-title">Choose a page</strong>
                </div>
                <button
                  aria-label="Close page picker"
                  @click="closeMobileSheet"
                >
                  <X :size="19" />
                </button>
              </div>
              <div class="mobile-page-grid">
                <button
                  v-for="item in document.pages"
                  :key="`mobile-${item.page_number}`"
                  :class="{ selected: item.page_number === page }"
                  :aria-current="item.page_number === page ? 'page' : undefined"
                  @click="selectPage(item.page_number)"
                >
                  <FileText :size="18" /><span
                    >Page {{ item.page_number }}</span
                  >
                </button>
              </div>
            </section>
          </section></template
        >
      </main>
    </div>
    <dialog ref="chatMenu" id="saved-chat-menu" class="chat-context-menu" :style="menuPosition"
      aria-label="Saved chat options" @cancel.prevent.stop="closeChatMenu" @keydown.esc.stop
      @keydown="menuKeydown" @click="menuOutside">
      <p class="chat-menu-title">{{ menuChat?.title }}</p>
      <div role="menu" aria-label="Saved chat actions">
        <button role="menuitem" tabindex="0" @click="openMenuConversation"><MessageSquare :size="17" /> Open chat</button>
        <button role="menuitem" tabindex="-1" class="menu-delete" @click="deleteMenuConversation"><Trash2 :size="17" /> Delete chat</button>
      </div>
    </dialog>
    <ConfirmDialog
      v-if="deleteTarget"
      :title="deleteTarget.title"
      :message="deleteTarget.message"
      :confirm-label="deleteTarget.kind === 'history' ? 'Clear history' : deleteTarget.kind === 'library' ? 'Clear library' : deleteTarget.kind === 'chat' ? 'Delete chat' : 'Delete PDF'"
      :busy="deleting"
      @cancel="!deleting && (deleteTarget = null)"
      @confirm="confirmDelete"
    />
  </div>
</template>
