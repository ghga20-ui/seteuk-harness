// 검수템플릿.html(최종 검수 화면)의 계산·산출 로직을 DOM 없이 검증한다.
// 등장인물은 전부 가상이다. 공통 하네스의 reporter·RULES는 그대로 쓰되,
// 대상 파일이 도구.html이 아니므로 로더는 이 파일 안에 따로 둔다.
import { readFileSync } from "node:fs";
import { reporter, RULES } from "./harness.mjs";

/** 검수템플릿.html의 메인 스크립트를 DOM 껍데기 위에서 실행한다. */
function loadFinal() {
  const html = readFileSync(new URL("../검수템플릿.html", import.meta.url), "utf-8");
  const js = html.split("<script>")[1].split("</script>")[0];

  const els = new Map();
  const make = () => ({
    innerHTML: "", textContent: "", value: "", disabled: false, hidden: false,
    files: [], dataset: {}, style: {},
    addEventListener() {}, removeEventListener() {}, setAttribute() {}, removeAttribute() {},
    click() {}, focus() {}, appendChild() {}, remove() {}, scrollIntoView() {},
    querySelector: () => null, querySelectorAll: () => [],
    closest: () => null,
    classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
  });
  const document = {
    getElementById(id) {
      if (!els.has(id)) els.set(id, make());
      return els.get(id);
    },
    createElement: make,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
  };
  const window = { addEventListener() {} };
  new Function("document", "window", "alert", "confirm", "TextEncoder",
    js.replace(/^"use strict";/, "") + "\nwindow.TOOLS = window.TOOLS;"
  )(document, window, () => {}, () => true, TextEncoder);
  return { ...window.TOOLS, els, document };
}

const T = loadFinal();
const { ok, done } = reporter();

const BUNDLE = () => ({
  활동명: "가상 활동",
  목표바이트: 700, 상한바이트: 760,
  금지어: RULES.금지어휘, 금지문자패턴: RULES.금지문자패턴,
  students: [
    { 토큰: "S-0001", 학번: "30101", 이름: "가상갑", 반: "1반", 톤등급: "중",
      핵심소재: "가상의 책(작가)", 세특: "가상 활동에서 성실히 참여함.", 비고: "", 예외: false,
      원문: "개령동 무덤 앞에서 제문을 읽는 대목이 오래 남았다.", 우선검토: [],
      짝: [{ n: 1, 세특: "성실히 참여함", 원문: "제문을 읽는 대목" }] },
    { 토큰: "S-0002", 학번: "30102", 이름: "가상을", 반: "1반", 톤등급: "상",
      핵심소재: "", 세특: "가상 활동에서 깊이 탐구함.", 비고: "검토 필요", 예외: false,
      원문: "원문 둘", 우선검토: ["검토 필요", "분량 미달"] },
    { 토큰: null, 학번: "30103", 이름: "가상병", 반: "2반", 톤등급: "중하",
      핵심소재: "", 세특: "가상 활동에 참여함.", 비고: "미제출", 예외: true,
      원문: "", 우선검토: ["토큰 없음"] },
  ],
});

// ── 기본 계산 ──────────────────────────────────────────────────
ok(T.U8("가나다") === 9, "UTF-8은 한글 3바이트", T.U8("가나다"));
ok(T.U8("abc") === 3, "영문은 1바이트");

// ── 짝 렌더 — 번호가 양쪽에 붙는다 ──────────────────────────────
{
  const 원문 = "학생이 개령동 무덤 앞에서 제문을 읽는 장면을 골랐다.";
  const 세특 = "개령동 제문 장면을 근거로 삼아 해석함.";
  const plan = T.planPairMarks(원문, 세특,
    [{ n: 1, 세특: "개령동 제문 장면", 원문: "개령동 무덤 앞에서 제문을 읽는" }], []);
  ok(plan.실패 === 0, "양쪽 다 있으면 실패 0", plan.실패);
  ok(plan.짝.length === 1, "짝 1건이 잡힌다");
  const srcHtml = T.renderMarked(원문, plan.짝.map(p =>
    ({ start: p.원문시작, end: p.원문끝, cls: "mk", attr: ` data-n="${T.numLabel(p.n)}"` })));
  const dstHtml = T.renderMarked(세특, plan.짝.map(p =>
    ({ start: p.세특시작, end: p.세특끝, cls: "mk", attr: ` data-n="${T.numLabel(p.n)}"` })));
  ok(srcHtml.includes('data-n="①"'), "원문 쪽에 번호 ①이 붙는다", srcHtml);
  ok(dstHtml.includes('data-n="①"'), "세특 쪽에도 같은 번호 ①이 붙는다", dstHtml);
  ok(T.numLabel(2) === "②" && T.numLabel(3) === "③", "번호는 ①②③ 순서다");
}

// ── 짝 매칭 실패 — 조용히 생략하지 않고 센다 ─────────────────────
{
  const plan = T.planPairMarks("원문에 그 말이 없다", "세특에도 그 말이 없다",
    [{ n: 1, 세특: "없는 구절", 원문: "역시 없는 구절" }], []);
  ok(plan.짝.length === 0 && plan.실패 === 1, "못 찾은 짝은 표시하지 않고 실패로 센다",
     JSON.stringify(plan));
  // 한쪽만 맞아도 짝으로 그리지 않는다 — 반쪽 표시는 오독을 만든다
  const half = T.planPairMarks("여기 있는 구절", "세특에는 없다",
    [{ n: 1, 세특: "없는 구절", 원문: "있는 구절" }], []);
  ok(half.짝.length === 0 && half.실패 === 1, "한쪽만 맞으면 실패로 센다");
}

// ── 짝없음 — 본문 안 꼬리표 대상, 못 찾으면 역시 센다 ─────────────
{
  const 세특 = "모둠 토의에서 상반된 해석을 검토함. 남은 문장.";
  const plan = T.planPairMarks("원문", 세특, [], ["모둠 토의에서 상반된 해석을 검토함."]);
  ok(plan.짝없음.length === 1 && plan.실패 === 0, "짝없음 구절을 찾는다");
  const html = T.renderMarked(세특, plan.짝없음.map(m =>
    ({ start: m.시작, end: m.끝, cls: "nopair" })));
  ok(html.includes('class="nopair"'), "짝없음 구절에 꼬리표 표식이 붙는다");
  const miss = T.planPairMarks("원문", 세특, [], ["세특에 없는 문장"]);
  ok(miss.짝없음.length === 0 && miss.실패 === 1, "못 찾은 짝없음도 실패로 센다");
}

// ── </script> 이스케이프 — 렌더와 주입 규약 왕복 ─────────────────
{
  const 원문 = "학생이 이렇게 썼다면: </script><h1>깨짐</h1>";
  const html = T.renderMarked(원문, []);
  ok(!html.includes("</script>"), "렌더된 본문에 닫는 스크립트 태그가 없다", html);
  ok(html.includes("&lt;/script&gt;"), "꺾쇠가 문자로 이스케이프된다");
  // 생성기와 같은 규약: JSON 문자열의 < 를 < 로 바꿔도 파싱하면 원문 그대로다
  const bundle = BUNDLE();
  bundle.students[0].원문 = 원문;
  const payload = JSON.stringify(bundle).replace(/</g, "\\u003c");
  ok(!payload.includes("<"), "심을 payload에 꺾쇠가 남지 않는다");
  const back = JSON.parse(payload);
  ok(back.students[0].원문 === 원문, "이스케이프 왕복 후 원문이 그대로다");
}

// ── 로드 — 우선 검토 정렬, 검수완료 존중 ────────────────────────
T.REVIEW.load(BUNDLE());
{
  const d = T.REVIEW.getData();
  ok(d.students[0].우선검토.length >= d.students[d.students.length - 1].우선검토.length,
     "우선 검토 대상이 앞으로 정렬됨");
}
{
  const b = BUNDLE();
  b.students[0].검수완료 = true;
  T.REVIEW.load(b);
  const d = T.REVIEW.getData();
  ok(d.students.some(s => s.검수완료 === true), "심은 데이터의 검수완료 표시를 지우지 않는다");
}

// ── 마치고 다음 — 검수 완료 행으로는 이동하지 않는다 ─────────────
{
  const students = [
    { 검수완료: false }, { 검수완료: true }, { 검수완료: false }, { 검수완료: true },
  ];
  ok(T.nextUndoneIndex(students, 0) === 2, "다음 미검수 행으로 건너뛴다",
     T.nextUndoneIndex(students, 0));
  ok(T.nextUndoneIndex(students, 2) === 0, "뒤에 없으면 앞의 미검수 행으로 돈다");
  const allDone = [{ 검수완료: true }, { 검수완료: true }];
  ok(T.nextUndoneIndex(allDone, 0) === null, "전원 마치면 이동할 곳이 없다");
}

// ── 금지어 ─────────────────────────────────────────────────────
T.REVIEW.load(BUNDLE());
ok(T.REVIEW.bannedHits("승패를 넘어선 태도").includes("넘어"), "금지어를 잡는다");
ok(T.REVIEW.bannedHits('그는 "말했다"').includes('"'), "금지문자(큰따옴표)를 잡는다");
ok(T.REVIEW.bannedHits("평범한 문장을 적었다").length === 0, "깨끗하면 잡지 않는다");

// ── diff 무실명 / 검수본 실명 ──────────────────────────────────
T.REVIEW.load(BUNDLE());
{
  const d = T.REVIEW.getData();
  d.students.find(s => s.토큰 === "S-0001").세특 = "가상 활동에서 차분하게 참여함.";
  const out = T.REVIEW.buildOutputs();
  ok(out.diff.변경.length === 1, "수정 1건이 잡힌다");
  ok(out.diff.변경[0].전.includes("성실히") && out.diff.변경[0].후.includes("차분하게"),
     "전/후 문장이 실린다");
  const diffText = JSON.stringify(out.diff);
  const names = ["가상갑", "가상을", "가상병"], ids = ["30101", "30102", "30103"];
  ok(!names.some(n => diffText.includes(n)), "diff에 이름이 없다");
  ok(!ids.some(i => diffText.includes(i)), "diff에 학번이 없다");
  const bonText = JSON.stringify(out.검수본);
  ok(names.every(n => bonText.includes(n)), "검수본에는 실명이 남는다");
  ok(out.검수본.classes.length === 2, "검수본은 반별로 나뉜다");
}

// ── 메모만 남겨도 diff에 잡힌다 ────────────────────────────────
T.REVIEW.load(BUNDLE());
{
  const d = T.REVIEW.getData();
  d.students[0].검수메모 = "표현이 과함";
  const out = T.REVIEW.buildOutputs();
  ok(out.diff.변경.length === 1 && out.diff.변경[0].검수메모 === "표현이 과함",
     "수정 없이 메모만 있어도 잡힌다");
}

// ── 2단계 저장 게이트 ──────────────────────────────────────────
T.REVIEW.load(BUNDLE());
ok(T.REVIEW.canSaveLocal() === false, "AI용을 저장하기 전에는 실명 저장이 닫혀 있다");
T.REVIEW.markAiSaved();
ok(T.REVIEW.canSaveLocal() === true, "AI용을 저장하면 실명 저장이 열린다");
T.REVIEW.load(BUNDLE());
ok(T.REVIEW.canSaveLocal() === false, "다시 로드하면 게이트가 다시 닫힌다");

// ── 미저장 수정 감지 (beforeunload 조건) ────────────────────────
T.REVIEW.load(BUNDLE());
ok(T.REVIEW.isDirty() === false, "로드 직후에는 미저장 수정이 없다");
{
  const d = T.REVIEW.getData();
  d.students[0].세특 = d.students[0].세특 + " 고침.";
  ok(T.REVIEW.isDirty() === true, "고치면 미저장 수정으로 잡힌다");
  T.REVIEW.markAiSaved();
  ok(T.REVIEW.isDirty() === false, "저장하면 미저장 수정이 풀린다");
}

// ── 확정 문구가 화면에 있다 ────────────────────────────────────
{
  const html = readFileSync(new URL("../검수템플릿.html", import.meta.url), "utf-8");
  ok(html.includes("왼쪽이 학생이 쓴 글, 오른쪽이 세특 초안입니다. 오른쪽만 고칠 수 있습니다."),
     "확정 문구 1(좌우 안내)이 있다");
  ok(html.includes("①② 같은 번호가 붙은 두 곳은 같은 내용입니다."),
     "확정 문구 2(짝 안내)가 있다");
  ok(html.includes("저장은 두 번 누릅니다."), "확정 문구 3(2단계 저장)이 있다");
  ok(html.includes("학생 실명이 있는 화면입니다 — 화면을 공유하거나 자리를 비울 때 닫아 주세요."),
     "확정 문구 4(상단 실명 경고)가 있다");
  ok(html.includes("원문 ①과 짝지었습니다 — 맞는지 봐 주세요") ||
     html.includes("과 짝지었습니다 — 맞는지 봐 주세요"),
     "짝 있음도 단정하지 않는 어법이 있다");
  ok(html.includes("수업에서 실제 있었던 일이면"), "짝 없음 유보 어법이 있다");
  ok(!html.includes("명조") && !html.includes("고딕이"), "교사에게 서체 용어를 말하지 않는다");
  ok(!html.includes("순서가 곧 경계"), "격언식 문구가 없다");
  ok(html.includes("__검수데이터__"), "데이터 플레이스홀더가 있다");
}

done();
