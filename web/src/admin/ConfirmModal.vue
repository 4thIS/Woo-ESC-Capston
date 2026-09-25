<script setup lang="ts">
import Button from '@/components/ui/Button.vue'
import Modal from '@/components/ui/Modal.vue'

// 확인 모달 — 본문에 지울 대상을 그대로 적는다. danger 는 여기서만 (components.md Modal·Button)
withDefaults(
  defineProps<{
    open: boolean
    title: string
    lines: string[]
    confirmLabel?: string
    danger?: boolean
    loading?: boolean
  }>(),
  { confirmLabel: '삭제', danger: true, loading: false },
)
const emit = defineEmits<{ confirm: []; close: [] }>()
</script>

<template>
  <Modal :open="open" :title="title" size="sm" @close="emit('close')">
    <p v-for="(line, i) in lines" :key="i" class="confirm__line">{{ line }}</p>
    <template #footer>
      <Button variant="secondary" @click="emit('close')">취소</Button>
      <Button
        :variant="danger ? 'danger' : 'primary'"
        :loading="loading"
        @click="emit('confirm')"
        >{{ confirmLabel }}</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.confirm__line {
  margin: 0 0 var(--space-2);
}
</style>
