# 기준 점수 — 원본 Gemma 4 E2B 예문 없음

- 문장 수: 381

## 합격선

| 지표 | 값 | 합격선 | 판정 |
|---|---|---|---|
| intent 정확도 | 29.7% | ≥ 97.0% | ❌ |
| 칸 정확도 | 11.9% | ≥ 95.0% | ❌ |
| 양식 전체 일치 | 16.0% | ≥ 90.0% | ❌ |
| 형식 오류 (강제 없음) | 63.0% | ≤ 1.0% | ❌ |
| 위험 오류 | 0.0% | ≤ 0.5% | ✅ |
| 응답 시간 평균 | — | ≤ 5000 ms | — |

**종합: 불합격**

## intent 별

| intent | n | intent 정확도 | 전체 일치 |
|---|---|---|---|
| ask.free_rooms | 20 | 60.0% | 0.0% |
| ask.node | 15 | 73.3% | 66.7% |
| ask.requests | 17 | 70.6% | 52.9% |
| ask.schedule | 20 | 80.0% | 15.0% |
| cancel | 16 | 43.8% | 43.8% |
| class.add | 21 | 0.0% | 0.0% |
| class.change | 19 | 0.0% | 0.0% |
| class.remove | 16 | 0.0% | 0.0% |
| event.add | 37 | 0.0% | 0.0% |
| event.change | 21 | 33.3% | 0.0% |
| event.remove | 19 | 31.6% | 5.3% |
| exam.add | 19 | 5.3% | 0.0% |
| exam.change | 16 | 0.0% | 0.0% |
| exam.remove | 16 | 68.8% | 56.2% |
| fill | 52 | 0.0% | 0.0% |
| request.approve | 19 | 42.1% | 10.5% |
| request.reject | 18 | 44.4% | 33.3% |
| unknown | 20 | 70.0% | 70.0% |

## 틀린 문장 (앞 30개)

- `h-A002` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 본관 301 담주 월~금 중간고사'`
  - 정답: `{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["본관 301"],"when":"담주 월~금"}}`
  - 출력: `{"v":1,"intent":"exam.add","target":{"rooms":["본관 301"],"when":["담주 월~금"],"time":null,"type":"시험","subject":null,"professor":null,"reason":null,"requester":null},"set":{}}`
- `h-A003` 
  - 입력: `'상태: exam.add | 강의실 802, 804 | 기간 ?\n질문: 시험기간은 언제부터 언제까지인가요? (예: 12/15~12/19)\n관리자: 근데 금요일 빈 강의실 있어?'`
  - 정답: `{"v":1,"intent":"ask.free_rooms","target":{"when":"금요일"},"set":{}}`
  - 출력: `{"v":1,"intent":"ask.free_rooms","target":{"rooms":["802","804"]},"set":{}}`
- `h-A004` 형식: 키는 v·intent·target·set 넷
  - 입력: `'상태: ask.free_rooms | 날짜 ?\n질문: 언제 빈 강의실을 찾을까요? (예: 이번 주 금요일 오후)\n관리자: 낼 3시부터'`
  - 정답: `{"v":1,"intent":"fill","target":{},"set":{"when":"낼","time":"3시부터"}}`
  - 출력: `{"v":1,"intent":"ask.free_rooms","target":{"날짜":"낼","time":"3시"}}`
- `h-A006` 형식: set.when 는 1~40자 문자열
  - 입력: `'상태: event.add | 날짜 12/9 | 시각 14시~17시 | 유형 대여 | 이름 정전 대비 | 강의실 ?\n질문: 어느 강의실인가요? (예: 803, 공학관 803, 8층 전체)\n관리자: 공학관 803호요'`
  - 정답: `{"v":1,"intent":"fill","target":{},"set":{"rooms":["공학관 803호"]}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["공학관 803"]},"set":{"when":["12/9"],"time":["14시~17시"],"type":"대여","subject":"정전 대비","requester":""}}`
- `h-A007` 형식: target 에 모르는 칸 ['날짜']
  - 입력: `'관리자: 12월 10일 802 휴강 취소'`
  - 정답: `{"v":1,"intent":"event.remove","target":{"rooms":["802"],"when":"12월 10일","type":"휴강"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.remove","target":{"날짜":"12월 10일"},"set":{"type":"휴강"}}`
- `h-A008` 형식: target.when 는 1~40자 문자열
  - 입력: `'상태: event.add | 강의실 802 | 날짜 12/10 | 유형 휴강\n질문: 확인 화면을 보고 [적용]을 눌러 주세요. 바꿀 것이 있으면 말씀해 주세요.\n관리자: 날짜 12/8로'`
  - 정답: `{"v":1,"intent":"fill","target":{},"set":{"when":"12/8"}}`
  - 출력: `{"v":1,"intent":"event.change","target":{"rooms":["802"],"when":["12/8"],"time":null,"type":"휴강","subject":null,"professor":null,"reason":null,"requester":null},"set":{"when":["12/8"]}}`
- `h-A009` 형식: set.when 는 1~40자 문자열
  - 입력: `'상태: event.add | 강의실 803 | 시각 3시~5시 | 유형 특강 | 이름 진로 특강 | 날짜 ?\n질문: 날짜는 언제인가요? (예: 12/3, 이번 주 금요일)\n관리자: 담주 목, 801도 같이'`
  - 정답: `{"v":1,"intent":"fill","target":{},"set":{"rooms":["801"],"when":"담주 목"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["803","801"]},"set":{"when":["다음 주 목요일"],"time":["3시~5시"],"type":["특강"],"subject":["진로 특강"],"professor":null,"reason":null,"requester":null}}`
- `h-A010` 형식: target.rooms 는 1~30개, 각 1~20자 문자열
  - 입력: `'관리자: 공학관 803호 12/5 오후 2시부터 4시까지 대여 동아리 총회'`
  - 정답: `{"v":1,"intent":"event.add","target":{},"set":{"rooms":["공학관 803호"],"when":"12/5","time":"오후 2시부터 4시까지","type":"대여","subject":"동아리 총회"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":"공학관 803호","when":"12/5","time":"오후 2시부터 4시까지","type":"대여","subject":"동아리 총회"},"set":{}}`
- `h-A011` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 801 803 12/15~12/19 시험기간'`
  - 정답: `{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["801","803"],"when":"12/15~12/19"}}`
  - 출력: `{"v":1,"intent":"exam.add","target":{"rooms":["801","803"],"when":["12/15~12/19"]},"set":{}}`
- `h-A012` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 803 금 3~6시 특강 알고리즘 특강'`
  - 정답: `{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],"when":"금","time":"3~6시","type":"특강","subject":"알고리즘 특강"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["803"],"when":{"time":"3~6시"},"type":"특강","subject":"알고리즘","professor":null,"reason":null,"requester":null},"set":{}}`
- `h-A013` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 담주 화 10시~12시 본관 2층 빈 교실'`
  - 정답: `{"v":1,"intent":"ask.free_rooms","target":{"rooms":["본관 2층"],"when":"담주 화","time":"10시~12시"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["본관 2층 빈 교실"],"when":["화"],"time":["10시~12시"],"type":["빈강의실"]},"set":{}}`
- `h-A015` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 805호 시험기간 등록 12/16-12/22'`
  - 정답: `{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["805호"],"when":"12/16-12/22"}}`
  - 출력: `{"v":1,"intent":"exam.add","target":{"rooms":["805"],"when":{"날짜":"12/16-12/22"}},"set":{}}`
- `h-A016` 
  - 입력: `'관리자: 801 내일 신청 승인'`
  - 정답: `{"v":1,"intent":"request.approve","target":{"rooms":["801"],"when":"내일"},"set":{}}`
  - 출력: `{"v":1,"intent":"request.approve","target":{"rooms":["801"]},"set":{}}`
- `h-A017` 
  - 입력: `'관리자: 802, 804 시험기간 다음주'`
  - 정답: `{"v":1,"intent":"exam.add","target":{},"set":{"rooms":["802","804"],"when":"다음주"}}`
  - 출력: `{"v":1,"intent":"exam.add","target":{"rooms":["802","804"]},"set":{"when":"다음주"}}`
- `h-A018` 형식: set.when 는 1~40자 문자열
  - 입력: `'관리자: 802 월수금 기초수학 월수로 줄여줘'`
  - 정답: `{"v":1,"intent":"class.change","target":{"rooms":["802"],"when":"월수금","subject":"기초수학"},"set":{"when":"월수"}}`
  - 출력: `{"v":1,"intent":"class.change","target":{"rooms":["802"]},"set":{"when":["월수금"],"time":null,"type":"수업","subject":"기초수학","professor":null,"reason":null,"requester":null}}`
- `h-A019` 형식: target.rooms 는 1~30개, 각 1~20자 문자열
  - 입력: `'관리자: 강의실 하나 새로 만들어줘'`
  - 정답: `{"v":1,"intent":"unknown","target":{},"set":{}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":[]},"set":{"rooms":["새 강의실"]}}`
- `h-A021` 
  - 입력: `'관리자: 공학관 805호 금 캡스톤디자인 없애'`
  - 정답: `{"v":1,"intent":"class.remove","target":{"rooms":["공학관 805호"],"when":"금","subject":"캡스톤디자인"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.remove","target":{"rooms":["공학관 805호"]},"set":{}}`
- `h-A022` 형식: JSON 이 아님: Expecting ',' delimiter
  - 입력: `'관리자: 낼 801 9시부터 11시 보강 자료구조'`
  - 정답: `{"v":1,"intent":"event.add","target":{},"set":{"rooms":["801"],"when":"낼","time":"9시부터 11시","type":"수업","subject":"자료구조"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["801"],"when":{"time":"9시부터11시"},"set":{"type":"수업","subject":"보강","professor":null,"reason":null,"requester":null}}`
- `h-A024` 형식: set.when 는 1~40자 문자열
  - 입력: `'관리자: 공학관 805호 금 14시~17시 캡스톤디자인 박지안'`
  - 정답: `{"v":1,"intent":"class.add","target":{},"set":{"rooms":["공학관 805호"],"when":"금","time":"14시~17시","subject":"캡스톤디자인","professor":"박지안"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["공학관 805호"]},"set":{"when":["금"],"time":["14시~17시"],"type":["수업"],"subject":["캡스톤디자인"],"professor":["박지안"],"requester":""}}`
- `h-A025` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 담주 화 자료구조 휴강 수요일로 바꿔'`
  - 정답: `{"v":1,"intent":"event.change","target":{"when":"담주 화","type":"휴강","subject":"자료구조"},"set":{"when":"수요일"}}`
  - 출력: `{"v":1,"intent":"event.change","target":{"when":["담주 화"]},"set":{"when":["수요일"]}}`
- `h-A026` 형식: 키는 v·intent·target·set 넷
  - 입력: `'관리자: 802 월수금 기초수학 폐강'`
  - 정답: `{"v":1,"intent":"class.remove","target":{"rooms":["802"],"when":"월수금","subject":"기초수학"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.remove","target":{"rooms":["802"],"when":["월수금"],"type":"휴강","subject":"기초수학"}}`
- `h-A027` 형식: target.rooms 는 1~30개, 각 1~20자 문자열
  - 입력: `'관리자: 담주 화 본관 2층 204 4시~6시 특강 반도체 특강 담당 김서준교수'`
  - 정답: `{"v":1,"intent":"event.add","target":{},"set":{"rooms":["본관 2층 204"],"when":"담주 화","time":"4시~6시","type":"특강","subject":"반도체 특강","professor":"김서준교수"}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":"본관 2층 204"},"set":{"when":"담주 화","time":"4시~6시","type":"특강","subject":"반도체","professor":"김서준교수"}}`
- `h-A028` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 801 12/15~19 시험기간 삭제'`
  - 정답: `{"v":1,"intent":"exam.remove","target":{"rooms":["801"],"when":"12/15~19"},"set":{}}`
  - 출력: `{"v":1,"intent":"exam.remove","target":{"rooms":["801"],"when":["12/15~19"]},"set":{}}`
- `h-A029` 형식: target.when 는 1~40자 문자열
  - 입력: `'관리자: 803 내일 3시 행사 5시까지로 연장'`
  - 정답: `{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":"내일","time":"3시"},"set":{"time":"5시까지"}}`
  - 출력: `{"v":1,"intent":"event.change","target":{"rooms":["803"],"when":["내일"],"time":["3시","5시"],"type":["행사"]},"set":{"time":["5시"]}}`
- `h-A030` 
  - 입력: `'상태: event.add | 강의실 803 | 유형 특강 | 날짜 ?\n질문: 날짜는 언제인가요? (예: 12/3, 이번 주 금요일)\n관리자: 아 그만'`
  - 정답: `{"v":1,"intent":"cancel","target":{},"set":{}}`
  - 출력: `{"v":1,"intent":"event.remove","target":{"rooms":["803"],"type":"특강"},"set":{}}`
- `h-A031` 형식: set.when 는 1~40자 문자열
  - 입력: `'관리자: 본관 2층 204 12/9 일정'`
  - 정답: `{"v":1,"intent":"ask.schedule","target":{"rooms":["본관 2층 204"],"when":"12/9"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["본관 2층 204"]},"set":{"when":["12/9"],"time":null,"type":null,"subject":null,"professor":null,"reason":null,"requester":null}}`
- `h-A033` 
  - 입력: `'관리자: 본관 2층 204 수 영어회화 802로 이동'`
  - 정답: `{"v":1,"intent":"class.change","target":{"rooms":["본관 2층 204"],"when":"수","subject":"영어회화"},"set":{"rooms":["802"]}}`
  - 출력: `{"v":1,"intent":"event.change","target":{"rooms":["본관 2층 204"]},"set":{"rooms":["802"]}}`
- `h-A034` 형식: target.rooms 는 1~30개, 각 1~20자 문자열
  - 입력: `'관리자: 내일 2시부터 4시 비는 방 있나'`
  - 정답: `{"v":1,"intent":"ask.free_rooms","target":{"when":"내일","time":"2시부터 4시"},"set":{}}`
  - 출력: `{"v":1,"intent":"ask.free_rooms","target":{"rooms":null},"set":{"rooms":["빈 강의실"]}}`
- `h-A035` 형식: 키는 v·intent·target·set 넷
  - 입력: `'상태: event.remove | 강의실 803 | 날짜 12/5\n질문: 몇 시 일정인가요? 과목·행사 이름으로 알려 주셔도 됩니다.\n관리자: 3시 특강'`
  - 정답: `{"v":1,"intent":"fill","target":{},"set":{"time":"3시","type":"특강"}}`
  - 출력: `{"v":1,"intent":"event.remove","target":{"rooms":["803"],"when":{"날짜":"12/5"},"time":"3시","type":"특강"}}`
- `h-A036` 형식: set.when 는 1~40자 문자열
  - 입력: `'상태: event.add | 강의실 803 | 날짜 12/5 | 유형 특강 | 이름 ?\n질문: 특강 이름은 무엇인가요?\n관리자: 801 내일 신청 승인'`
  - 정답: `{"v":1,"intent":"request.approve","target":{"rooms":["801"],"when":"내일"},"set":{}}`
  - 출력: `{"v":1,"intent":"event.add","target":{"rooms":["801"]},"set":{"when":["내일"],"time":null,"type":"수업","subject":null,"professor":null,"reason":null,"requester":null}}`
