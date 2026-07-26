// 검수 화면의 계산·산출 로직을 DOM 없이 검증한다. 등장인물은 전부 가상이다.
import { loadTools, reporter, RULES } from "./harness.mjs";

// 픽스처를 지어내지 말고 실제 규칙 정본에서 읽는다 — 내가 가정한 형태로
// 테스트를 만들었다가 금지문자 검사가 무력한 것을 놓친 적이 있다.
const T = loadTools();
const mod = { ...T.REVIEW, U8: T.U8, B2: T.B2 };
const { ok, done } = reporter();

const BUNDLE = () => ({
  활동명: "가상 활동",
  목표바이트: 700, 상한바이트: 760,
  금지어: RULES.금지어휘, 금지문자패턴: RULES.금지문자패턴,
  students: [
    { 토큰: "S-0001", 학번: "30101", 이름: "가상갑", 반: "1반", 톤등급: "중",
      핵심소재: "가상의 책(작가)", 세특: "가상 활동에서 성실히 참여함.", 비고: "", 예외: false,
      원문: "원문 하나", 우선검토: [] },
    { 토큰: "S-0002", 학번: "30102", 이름: "가상을", 반: "1반", 톤등급: "상",
      핵심소재: "", 세특: "가상 활동에서 깊이 탐구함.", 비고: "검토 필요", 예외: false,
      원문: "원문 둘", 우선검토: ["검토 필요", "분량 미달"] },
    { 토큰: null, 학번: "30103", 이름: "가상병", 반: "2반", 톤등급: "중하",
      핵심소재: "", 세특: "가상 활동에 참여함.", 비고: "미제출", 예외: true,
      원문: "", 우선검토: ["토큰 없음"] },
  ],
});

// ── 바이트 계산 ────────────────────────────────────────────────
ok(mod.U8("가나다") === 9, "UTF-8은 한글 3바이트", mod.U8("가나다"));
ok(mod.B2("가나다") === 6, "2바이트 기준은 한글 2바이트", mod.B2("가나다"));
ok(mod.U8("abc") === 3 && mod.B2("abc") === 3, "영문은 두 기준이 같다");

// ── 우선 검토가 위로 올라오는가 ─────────────────────────────────
mod.load(BUNDLE());
let d = mod.getData();
ok(d.students[0].우선검토.length >= d.students[d.students.length - 1].우선검토.length,
   "우선 검토 대상이 앞으로 정렬됨",
   JSON.stringify(d.students.map(s => s.우선검토.length)));

// ── 금지어 탐지 ────────────────────────────────────────────────
ok(mod.bannedHits("승패를 넘어선 태도").includes("넘어"), "금지어를 잡는다");
ok(mod.bannedHits('그는 "말했다"').includes('"'), "금지문자(큰따옴표)를 잡는다");
ok(mod.bannedHits("가·나 형태").includes("·"), "금지문자(가운뎃점)를 잡는다");
ok(mod.bannedHits("① 첫째").includes("①"), "금지문자(원문자)를 잡는다");
ok(mod.bannedHits("평범한 문장을 적었다").length === 0, "깨끗하면 잡지 않는다",
   JSON.stringify(mod.bannedHits("평범한 문장을 적었다")));

// ── 수정 없을 때 diff가 비어야 한다 ─────────────────────────────
mod.load(BUNDLE());
let out = mod.buildOutputs();
ok(out.diff.변경.length === 0, "수정이 없으면 diff가 비어 있다", JSON.stringify(out.diff.변경));
ok(out.검수본.classes.length === 2, "반별로 나뉜다", out.검수본.classes.length);

// ── 수정하면 전/후가 담긴다 ─────────────────────────────────────
mod.load(BUNDLE());
d = mod.getData();
const target = d.students.find(s => s.토큰 === "S-0001");
target.세특 = "가상 활동에서 차분하게 참여함.";
out = mod.buildOutputs();
ok(out.diff.변경.length === 1, "수정 1건이 잡힌다", out.diff.변경.length);
const ch = out.diff.변경[0];
ok(ch.토큰 === "S-0001", "토큰이 실린다");
ok(ch.전.includes("성실히") && ch.후.includes("차분하게"), "전/후 문장이 실린다");
ok(ch.바이트변화.전 > 0 && ch.바이트변화.후 > 0, "바이트 변화가 실린다");

// ── diff에 실명·학번이 없어야 한다 (이 페이지의 존재 이유) ────────
const diffText = JSON.stringify(out.diff);
const names = ["가상갑", "가상을", "가상병"], ids = ["30101", "30102", "30103"];
ok(!names.some(n => diffText.includes(n)), "diff에 이름이 없다");
ok(!ids.some(i => diffText.includes(i)), "diff에 학번이 없다");

// ── 검수본에는 실명이 있어야 한다 (로컬 보관용) ──────────────────
const bonText = JSON.stringify(out.검수본);
ok(names.every(n => bonText.includes(n)), "검수본에는 실명이 남는다");

// ── 메모만 남겨도 diff에 잡힌다 ─────────────────────────────────
mod.load(BUNDLE());
d = mod.getData();
d.students[0].검수메모 = "표현이 과함";
out = mod.buildOutputs();
ok(out.diff.변경.length === 1 && out.diff.변경[0].검수메모 === "표현이 과함",
   "수정 없이 메모만 있어도 잡힌다");

// ── 토큰 없는 학생도 빠지지 않는다 ──────────────────────────────
mod.load(BUNDLE());
d = mod.getData();
d.students.find(s => s.학번 === "30103").세특 = "가상 활동에 참여하였음.";
out = mod.buildOutputs();
ok(out.diff.변경.some(c => c.토큰 === null), "토큰 없는 학생의 수정도 담긴다");
ok(out.검수본.classes.flatMap(c => c.students).length === 3, "검수본에 전원이 담긴다");

done();
