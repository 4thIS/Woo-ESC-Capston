<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { POLICIES } from '../policies'
import StudentHeader from '../StudentHeader.vue'

// 약관 및 정책 — 로그인 없이 연다(가입 전에 읽는다). 문서는 주소를 가진 링크(/policies/:doc),
// 조항은 앵커(#p1). 폰은 문서 칩 + 접는 목차, 넓은 폭은 왼쪽에 문서·목차를 늘 펼친다
const route = useRoute()
const doc = computed(() => POLICIES.find((p) => p.id === route.params.doc) ?? POLICIES[0])
</script>

<template>
  <div class="pol">
    <StudentHeader title="약관 및 정책" back="/" back-label="메인 페이지" />
    <div class="pol__body">
      <aside class="pol__side">
        <nav class="pol__docs" aria-label="문서">
          <p class="pol__label">문서</p>
          <RouterLink
            v-for="p in POLICIES"
            :key="p.id"
            :to="`/policies/${p.id}`"
            class="pol__doc"
            :aria-current="p.id === doc.id ? 'page' : undefined"
            >{{ p.title }}</RouterLink
          >
        </nav>
        <p class="pol__label">목차</p>
        <ol class="pol__toc">
          <li v-for="s in doc.sections" :key="s.id">
            <a :href="`#${s.id}`">{{ s.title }}</a>
          </li>
        </ol>
      </aside>
      <main class="pol__main">
        <!-- 폰 — 문서가 늘어도 되게 가로로 넘기는 칩 줄 -->
        <nav class="pol__chips" aria-label="문서">
          <RouterLink
            v-for="p in POLICIES"
            :key="p.id"
            :to="`/policies/${p.id}`"
            class="pol__chip"
            :aria-current="p.id === doc.id ? 'page' : undefined"
            >{{ p.title }}</RouterLink
          >
        </nav>
        <article class="pol__doc-body">
          <header class="pol__head">
            <h2 class="pol__title">{{ doc.title }}</h2>
            <p class="pol__eff">시행일 {{ doc.effective }}</p>
          </header>
          <p class="pol__intro">{{ doc.intro }}</p>
          <details :key="doc.id" class="pol__tocbox">
            <summary>목차 {{ doc.sections.length }}개</summary>
            <ol class="pol__toc">
              <li v-for="s in doc.sections" :key="s.id">
                <a :href="`#${s.id}`">{{ s.title }}</a>
              </li>
            </ol>
          </details>
          <section
            v-for="s in doc.sections"
            :id="s.id"
            :key="s.id"
            class="pol__sec"
            :aria-labelledby="`${s.id}-h`"
          >
            <h3 :id="`${s.id}-h`" class="pol__sec-title">{{ s.title }}</h3>
            <template v-for="(b, i) in s.body" :key="i">
              <p v-if="'p' in b">{{ b.p }}</p>
              <ol v-else-if="'ol' in b">
                <li v-for="t in b.ol" :key="t">{{ t }}</li>
              </ol>
              <ul v-else-if="'ul' in b">
                <li v-for="t in b.ul" :key="t">{{ t }}</li>
              </ul>
              <div v-else class="pol__tbl">
                <table>
                  <thead>
                    <tr>
                      <th v-for="h in b.table.head" :key="h" scope="col">{{ h }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in b.table.rows" :key="r[0]">
                      <td>{{ r[0] }}</td>
                      <td>{{ r[1] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </section>
        </article>
      </main>
    </div>
  </div>
</template>

<style scoped>
.pol {
  min-height: 100vh;
  background: var(--surface);
}
.pol__side {
  display: none;
}
.pol__chips {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  overflow-x: auto;
  border-bottom: var(--border-thin) solid var(--line-1);
  scrollbar-width: none;
}
.pol__chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-full);
  color: var(--text-2);
  text-decoration: none;
  white-space: nowrap;
}
/* 고른 문서 — brand 없이 테두리·굵기로 (선택은 1차 액션이 아니다) */
.pol__chip[aria-current='page'] {
  border-color: var(--text-1);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
}
.pol__doc-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  max-width: 720px;
  padding: var(--space-5) var(--space-4) var(--space-7);
}
.pol__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.pol__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.pol__eff,
.pol__intro {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--text-3);
}
.pol__intro {
  color: var(--text-2);
}
.pol__tocbox {
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--sunken);
}
.pol__tocbox summary {
  display: flex;
  align-items: center;
  min-height: var(--control-height-md);
  padding: 0 var(--space-4);
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}
/* flex 라 기본 삼각형이 사라진다 — 펼칠 수 있다는 표시를 오른쪽에 */
.pol__tocbox summary::after {
  content: '▾';
  margin-left: auto;
  color: var(--text-3);
}
.pol__tocbox[open] summary::after {
  content: '▴';
}
.pol__tocbox .pol__toc {
  padding: 0 var(--space-4) var(--space-3);
}
.pol__toc {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}
.pol__toc a {
  display: block;
  padding: var(--space-2) 0;
  font-size: var(--font-size-sm);
  color: var(--text-2);
  text-decoration: none;
}
.pol__toc a:hover {
  color: var(--text-1);
}
/* 앵커로 갔을 때 붙박이 헤더(58px)에 제목이 가리지 않게 */
.pol__sec {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  scroll-margin-top: calc(58px + var(--space-4));
}
.pol__sec-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.pol__sec p,
.pol__sec li {
  margin: 0;
  line-height: 1.75;
}
.pol__sec ol,
.pol__sec ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding-left: 1.3em;
}
.pol__tbl {
  overflow-x: auto;
}
.pol__tbl table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}
.pol__tbl th,
.pol__tbl td {
  padding: var(--space-2);
  border-bottom: var(--border-thin) solid var(--line-1);
  text-align: left;
  vertical-align: top;
}
.pol__tbl th {
  background: var(--sunken);
  color: var(--text-2);
  font-weight: var(--font-weight-medium);
}
.pol__tbl td:first-child {
  white-space: nowrap;
}
/* 넓은 폭 — 학생 웹 넓은 폭 틀처럼 왼쪽 고정 칸 + 오른쪽 본문(최대 720px) */
@media (min-width: 640px) {
  .pol__body {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr);
  }
  .pol__side {
    position: sticky;
    top: 58px;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    align-self: start;
    /* 화면 높이만큼 — 목차가 짧아도 회색 칸이 중간에서 끊기지 않게, 길면 칸 안에서 스크롤 */
    height: calc(100vh - 58px);
    overflow-y: auto;
    padding: var(--space-5) var(--space-4);
    border-right: var(--border-thin) solid var(--line-2);
    background: var(--sunken);
  }
  .pol__side .pol__toc a {
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
  }
  .pol__chips,
  .pol__tocbox {
    display: none;
  }
  .pol__doc-body {
    padding: var(--space-6) var(--space-7) var(--space-7);
  }
}
.pol__docs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: var(--space-4);
}
.pol__label {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--text-3);
}
.pol__doc {
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  color: var(--text-2);
  text-decoration: none;
}
.pol__doc[aria-current='page'] {
  background: var(--surface);
  box-shadow: inset 0 0 0 var(--border-thin) var(--line-2);
  color: var(--text-1);
  font-weight: var(--font-weight-bold);
}
</style>
