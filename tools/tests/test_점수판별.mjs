// 점수 붙여넣기 판별을 DOM 없이 검증한다. 학번은 전부 가상이다.
import { readFileSync } from "node:fs";

const html = readFileSync(
  new URL("../명렬입력.html", import.meta.url),
  "utf-8"
);
const js = html.split("<script>")[1].split("</script>")[0];

// parseScores는 DOM에 의존하므로 최소한의 가짜 DOM을 세운다.
const els = {};
const mk = () => ({ innerHTML: "", textContent: "", value: "" });
for (const id of ["scorenotices", "scorestats", "scoredist", "scoresrc"]) els[id] = mk();
const document = {
  getElementById: id => els[id] || mk(),
  addEventListener: () => {},
  createElement: () => ({ click: () => {}, dataset: {} }),
};
const window = {};
const pure = js.slice(0, js.indexOf('document.getElementById("src").addEventListener'));
const fn = new Function("document", pure + "\nreturn { parseScores, state };");
const mod = fn(document);

function run(label, roster, paste, expect) {
  mod.state.students = roster.map(([sid, nm]) => ({ 학번: sid, 이름: nm, 제출: true, 중복: false }));
  mod.state.scores = [];
  els.scoresrc.value = paste;
  mod.parseScores();
  const got = mod.state.scores;
  const ok =
    got.length === expect.n &&
    (expect.first === undefined ||
      JSON.stringify(got[0]) === JSON.stringify(expect.first)) &&
    (expect.notice === undefined || els.scorenotices.innerHTML.includes(expect.notice));
  console.log(
    `${ok ? "PASS" : "★FAIL★"}  ${label} → ${got.length}건 ${JSON.stringify(got[0] || null)}` +
    (els.scorenotices.innerHTML ? `  [경고 있음]` : "")
  );
  if (!ok) console.log("      기대:", JSON.stringify(expect), "| 알림:", els.scorenotices.innerHTML.slice(0, 160));
}

const R = [["30101", "가상갑"], ["30102", "가상을"], ["30103", "가상병"]];

run("학번+점수", R, "30101\t15\n30102\t13\n30103\t9",
  { n: 3, first: { 학번: "30101", 점수: 15 } });

run("헤더 줄 포함", R, "학번\t점수\n30101\t15\n30102\t13\n30103\t9",
  { n: 3, first: { 학번: "30101", 점수: 15 } });

run("점수가 앞 열", R, "15\t30101\n13\t30102\n9\t30103",
  { n: 3, first: { 학번: "30101", 점수: 15 } });

run("여러 열 중 점수 열", R, "30101\t가상갑\t15\n30102\t가상을\t13\n30103\t가상병\t9",
  { n: 3 });

run("등급", R, "30101\t상\n30102\t중\n30103\t하",
  { n: 3, first: { 학번: "30101", 등급: "상" } });

run("숫자·등급 혼재 → 거부", R, "30101\t15\n30102\t중\n30103\t9",
  { n: 0, notice: "섞여" });

run("명렬에 없는 학번 섞임", R, "30101\t15\n39999\t20\n30102\t13\n30103\t9",
  { n: 3, notice: "명렬에 없는" });

run("일부 누락", R, "30101\t15\n30102\t13",
  { n: 2, notice: "점수가 붙여넣기에 없는" });

run("소수점 점수", R, "30101\t14.5\n30102\t13\n30103\t9",
  { n: 3, first: { 학번: "30101", 점수: 14.5 } });

run("학번 전혀 없음", R, "가상갑\t15\n가상을\t13", { n: 0, notice: "하나도 찾지 못했습니다" });
