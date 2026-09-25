import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default defineConfigWithVueTs(
  { name: 'app/files-to-lint', files: ['**/*.{ts,mts,tsx,vue}'] },
  { name: 'app/files-to-ignore', ignores: ['**/dist/**', '**/coverage/**'] },
  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  {
    name: 'app/boundary-admin',
    files: ['src/admin/**'],
    rules: { 'no-restricted-imports': ['error', { patterns: ['@/student/*', '**/student/**'] }] },
  },
  {
    name: 'app/boundary-student',
    files: ['src/student/**'],
    rules: { 'no-restricted-imports': ['error', { patterns: ['@/admin/*', '**/admin/**'] }] },
  },
  {
    name: 'app/boundary-shared',
    files: ['src/{api,lib,styles,components,auth}/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        { patterns: ['@/admin/*', '@/student/*', '**/admin/**', '**/student/**'] },
      ],
    },
  },
  {
    // ui 디자인 시스템 컴포넌트는 components.md 표의 단어 그대로 (Button·Badge·Skeleton) 쓴다
    name: 'app/ui-component-names',
    files: ['src/components/ui/**'],
    rules: { 'vue/multi-word-component-names': 'off' },
  },
  skipFormatting,
)
