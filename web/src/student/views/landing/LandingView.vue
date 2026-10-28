<script setup lang="ts">
import CtaLink from '../../CtaLink.vue'
import EpaperPreview from './EpaperPreview.vue'
import ResvPreview from './ResvPreview.vue'
import RoomListPreview from './RoomListPreview.vue'
import WeekPreview from './WeekPreview.vue'

// 로그인 전 `/` — 학교 소개가 아니라 학생이 할 수 있는 일 소개. 학교를 모르고 서버를 부르지 않는다 (landing.md)
const FEATURES = [
  {
    title: '지금 빈 강의실',
    text: '건물을 고르면 강의실마다 지금 수업 중인지, 언제까지 비어 있는지 보여요. 자주 가는 강의실은 ★ 로 맨 위에.',
    preview: 'rooms',
  },
  {
    title: '이번 주 시간표',
    text: '강의실 하나의 월~금 시간표를 한 화면에. 수업 · 시험 · 특강 · 내 예약이 같이 보여요.',
    preview: 'week',
  },
  {
    title: '예약 신청',
    text: '비어 있는 시간을 골라 신청하면 관리자가 승인해요. 7일 이내 · 비어 있는 시간만. 승인되면 시간에 맞춰 체크인.',
    preview: 'resv',
  },
  {
    title: '문 앞 화면과 같은 정보',
    text: '강의실 문 앞 전자종이와 웹이 같은 시간표를 봐요. 승인된 예약은 문 앞 화면에도 떠요.',
    preview: 'epaper',
  },
] as const
const STEPS = [
  ['학교 웹메일로 가입 신청', '메일로 링크가 와요. 5분 안에 열어 주세요.'],
  ['이름 · 학번 · 비밀번호 입력', '링크를 연 화면에서 계정을 마무리해요.'],
  ['관리자 승인 뒤 로그인', '승인되면 메일이 와요. 그때부터 로그인할 수 있어요.'],
] as const
</script>

<template>
  <div class="landing">
    <header class="lh">
      <span class="lh__brand">ESC</span>
      <nav class="lh__nav" aria-label="계정">
        <CtaLink to="/signup" variant="ghost" compact class="lh__signup">가입 신청</CtaLink>
        <CtaLink to="/login" variant="secondary" compact>로그인</CtaLink>
      </nav>
    </header>

    <main>
      <section class="hero band band--surface">
        <div class="wrap hero__grid">
          <div class="hero__text">
            <p class="hero__eyebrow">강의실 시간표 · 예약</p>
            <h1 class="hero__title">
              빈 강의실,<br class="hero__br" />
              폰으로 바로 확인하세요.
            </h1>
            <p class="hero__lead">
              지금 비어 있는 강의실을 찾고, 이번 주 시간표를 보고, 필요한 시간에 예약을 신청하세요.
              학교 웹메일로 가입하면 됩니다.
            </p>
            <div class="hero__actions">
              <!-- 이 화면의 유일한 brand 채움 -->
              <CtaLink to="/login" class="hero__btn">로그인</CtaLink>
              <CtaLink to="/signup" variant="secondary" class="hero__btn">가입 신청</CtaLink>
            </div>
            <p class="hero__note">학교 웹메일로 가입 · 관리자 승인 뒤 이용</p>
          </div>
          <RoomListPreview :rows="4" class="hero__preview" />
        </div>
      </section>

      <section class="band band--student" aria-labelledby="features-h">
        <div class="wrap">
          <h2 id="features-h" class="sec__title">학생이 할 수 있는 일</h2>
          <p class="sec__sub">복도에서 폰으로, 수업 사이 쉬는 시간에.</p>
          <ul class="features">
            <li v-for="f in FEATURES" :key="f.title" class="feature">
              <h3 class="feature__title">{{ f.title }}</h3>
              <p class="feature__text">{{ f.text }}</p>
              <!-- 미리보기는 카드 바닥에 — 설명 길이가 달라도 윗선이 한 줄로 선다 -->
              <div class="feature__preview">
                <RoomListPreview v-if="f.preview === 'rooms'" :rows="3" />
                <WeekPreview v-else-if="f.preview === 'week'" />
                <ResvPreview v-else-if="f.preview === 'resv'" />
                <EpaperPreview v-else />
              </div>
            </li>
          </ul>
        </div>
      </section>

      <section class="band band--surface band--line" aria-labelledby="steps-h">
        <div class="wrap how">
          <div>
            <h2 id="steps-h" class="sec__title">시작하는 방법</h2>
            <p class="sec__sub">처음 한 번만 하면 돼요.</p>
          </div>
          <ol class="steps">
            <li v-for="([t, d], i) in STEPS" :key="t" class="step">
              <span class="step__no num" aria-hidden="true">{{ i + 1 }}</span>
              <div>
                <h3 class="step__title">{{ t }}</h3>
                <p class="step__text">{{ d }}</p>
              </div>
            </li>
          </ol>
          <!-- 폰에서만 — 히어로까지 다시 올라가지 않게. 태블릿 이상은 헤더의 가입 신청으로 충분 -->
          <CtaLink to="/signup" variant="secondary" class="steps__cta">가입 신청하기</CtaLink>
        </div>
      </section>
    </main>

    <footer class="band band--surface band--line">
      <div class="wrap foot">
        <p class="foot__text">ESC — 전자종이 · LoRa 강의실 시간표 게시 시스템</p>
        <!-- 관리자 앱이라 라우터 이동이 아니라 페이지를 새로 연다 -->
        <a href="/admin/login" class="foot__admin">관리자 로그인</a>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* 세 폭(landing.md 「반응형」) — 폰 < 640 · 태블릿 640–1023 · 넓은 화면 ≥ 1024 */
.landing {
  min-height: 100vh;
  background: var(--surface);
}
.lh {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 58px;
  padding: 0 var(--space-4);
  border-bottom: var(--border-thin) solid var(--line-2);
  background: var(--surface);
}
.lh__brand {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}
.lh__nav {
  display: flex;
  gap: var(--space-2);
}
.lh__signup {
  display: none;
}
.wrap {
  padding: 0 var(--space-4);
}
.band {
  padding: var(--space-6) 0;
}
.band--surface {
  background: var(--surface);
}
.band--student {
  background: var(--bg-student);
}
.band--line {
  border-top: var(--border-thin) solid var(--line-2);
}
.hero {
  border-bottom: var(--border-thin) solid var(--line-2);
}
.hero__grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}
.hero__text {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.hero__text p,
.sec__sub,
.feature__text,
.step__text,
.foot__text {
  margin: 0;
}
.hero__eyebrow {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.hero__title {
  margin: 0;
  font-size: 26px;
  font-weight: var(--font-weight-bold);
  line-height: 1.3;
  text-wrap: balance;
}
.hero__lead {
  max-width: 520px;
  font-size: 16px;
  line-height: 1.65;
  color: var(--text-2);
}
.hero__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.hero__btn {
  min-height: 52px;
}
.hero__note {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.sec__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}
.sec__sub {
  margin-top: var(--space-1);
  color: var(--text-2);
}
.features {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
  margin: var(--space-5) 0 0;
  padding: 0;
  list-style: none;
}
/* 행 안에서 높이를 맞추고(grid stretch) 미리보기는 바닥에 */
.feature {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border: var(--border-thin) solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.feature__title {
  margin: 0;
  font-size: 17px;
  font-weight: var(--font-weight-bold);
}
.feature__text {
  font-size: 14px;
  color: var(--text-2);
}
.feature__preview {
  margin-top: auto;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--sunken);
}
.how {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
.steps {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.step {
  display: flex;
  gap: var(--space-3);
}
/* 현재 단계가 없는 안내라 번호를 칠하지 않는다 — line.3 테두리 원 */
.step__no {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  border: var(--border-thin) solid var(--line-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  color: var(--text-2);
}
.step__title {
  margin: 0 0 2px;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}
.step__text {
  font-size: var(--font-size-sm);
  color: var(--text-2);
}
.foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.band:has(.foot) {
  padding: var(--space-4) 0;
}
.foot__text {
  font-size: var(--font-size-xs);
  color: var(--text-3);
}
.foot__admin {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  font-size: var(--font-size-sm);
  color: var(--text-2);
}

@media (min-width: 640px) {
  .lh {
    padding: 0 40px;
  }
  .lh__signup {
    display: flex;
  }
  .wrap {
    padding: 0 40px;
  }
  .band {
    padding: var(--space-7) 0;
  }
  /* 태블릿: 가운데 정렬 한 칸 — 글 → 버튼(가로) → 미리보기(최대 440px) */
  .hero__grid {
    align-items: center;
    text-align: center;
  }
  .hero__text {
    align-items: center;
  }
  .hero__title {
    font-size: 32px;
  }
  .hero__br {
    display: none;
  }
  .hero__actions {
    flex-direction: row;
  }
  .hero__preview {
    width: 100%;
    max-width: 440px;
    text-align: left;
  }
  .features {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .steps__cta {
    display: none;
  }
}

@media (min-width: 1024px) {
  .lh {
    padding: 0 80px;
  }
  .wrap {
    max-width: calc(1120px + 160px);
    margin: 0 auto;
    padding: 0 80px;
  }
  /* 넓은 화면: 2단 — 왼쪽 글 + 버튼, 오른쪽 미리보기 440px, 세로 가운데 */
  .hero__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 440px;
    align-items: center;
    text-align: left;
  }
  .hero__text {
    align-items: flex-start;
  }
  .hero__title {
    font-size: 40px;
  }
  .hero__br {
    display: inline;
  }
  .features {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .how {
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr);
  }
}
</style>
