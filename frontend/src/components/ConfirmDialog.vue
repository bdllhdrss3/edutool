<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

const props = defineProps<{ title: string; message: string; confirmLabel: string; busy?: boolean }>()
const emit = defineEmits<{ cancel: []; confirm: [] }>()
const id = useId()
const dialog = ref<HTMLDialogElement | null>(null)
const cancelButton = ref<HTMLButtonElement | null>(null)
const submitted = ref(false)
let trigger: HTMLElement | null = null
watch(() => props.busy, value => { if (!value) submitted.value = false })
function cancel() {
  if (!props.busy && !submitted.value) emit('cancel')
}
function confirm() {
  if (props.busy || submitted.value) return
  submitted.value = true
  emit('confirm')
}
function outside(event: MouseEvent) {
  const element = dialog.value
  if (!element || event.target !== element) return
  const rect = element.getBoundingClientRect()
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) cancel()
}
onMounted(() => {
  trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  dialog.value?.showModal()
  cancelButton.value?.focus()
})
onBeforeUnmount(() => {
  dialog.value?.close()
  void nextTick(() => {
    if (trigger?.isConnected && trigger.getClientRects().length) trigger.focus({ preventScroll: true })
    else document.querySelector<HTMLElement>('.library-upload input, header .crumb')?.focus({ preventScroll: true })
  })
})
</script>

<template>
  <dialog ref="dialog" class="confirm-dialog" role="alertdialog" :aria-labelledby="`${id}-title`"
    :aria-describedby="`${id}-description`" :aria-busy="busy || submitted"
    @cancel.prevent.stop="cancel" @keydown.esc.stop @click="outside">
    <h2 :id="`${id}-title`">{{ title }}</h2>
    <p :id="`${id}-description`">{{ message }}</p>
    <div>
      <button ref="cancelButton" class="button secondary" type="button" autofocus :disabled="busy || submitted" @click="cancel">Cancel</button>
      <button class="button danger" type="button" :disabled="busy || submitted" @click="confirm">{{ busy || submitted ? 'Deleting…' : confirmLabel }}</button>
    </div>
  </dialog>
</template>