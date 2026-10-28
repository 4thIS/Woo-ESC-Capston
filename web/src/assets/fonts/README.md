# Pretendard 서브셋 (self-host)

- 출처: https://github.com/orioncactus/pretendard 태그 `v1.3.9` (`docs/design/tokens.md` §타이포 — CDN 이 아니라 self-host)
- 라이선스: SIL Open Font License 1.1. 원문은 `OFL.txt` (위 태그의 `LICENSE`)
- 서브셋 범위: KS X 1001 한글 2,350자 + 호환 자모(U+3131–U+318E) + ASCII(U+0020–U+007E) + 기호(`· ‹ › « » ① ② ③ ④ ⑤ ⑥ ⑦ • — – … ※ ○ ● ◐ ← → ↑ ↓ ▾ ▴ ✓ ✕ " " ' ' ℃ ° ± × ÷`)
- 실제 바이트 수: **457,552 B** (447 KiB) — 400 KB(409,600 B) 상한을 넘었다. `--no-hinting --desubroutinize` 를 시도했으나 오히려 커져(457,704 B) 기본 옵션 결과를 채택했다. spec §9 열린 결정 — PR 에서 mh 와 크기를 다시 정한다.

재생성 명령 (jsdelivr 경로가 `packages/pretendard/dist/...` 로 바뀌었다 — 태그 `v1.3.9` 기준):

```bash
cd web/src/assets/fonts
V=v1.3.9
curl -fsSLo "$TMP/pv.woff2" "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@$V/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2"
curl -fsSLo OFL.txt "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@$V/LICENSE"
python - > "$TMP/chars.txt" <<'PY'
def ks(c):
    try:
        return len(c.encode('euc-kr')) == 2  # Windows 의 euc-kr 은 2350자 밖도 자모 분해로 인코딩해 예외를 던지지 않는다
    except UnicodeEncodeError:
        return False
hangul = ''.join(c for c in map(chr, range(0xAC00, 0xD7A4)) if ks(c))
assert len(hangul) == 2350, len(hangul)
jamo = ''.join(map(chr, range(0x3131, 0x318F)))
ascii_ = ''.join(map(chr, range(0x20, 0x7F)))
extra = '·‹›«»①②③④⑤⑥⑦•—–…※○●◐←→↑↓▾▴✓✕“”‘’℃°±×÷'
print(hangul + jamo + ascii_ + extra, end='')
PY
uvx --from fonttools --with brotli pyftsubset "$TMP/pv.woff2" --text-file="$TMP/chars.txt" \
  --flavor=woff2 --layout-features='*' --output-file=PretendardVariable.subset.woff2
wc -c PretendardVariable.subset.woff2
```
