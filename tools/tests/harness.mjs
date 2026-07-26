// 도구.html의 스크립트를 DOM 없이 불러오는 공통 하네스.
// 브라우저를 띄울 수 없으므로 계산·판정·산출 로직만 검사한다.
import { readFileSync } from "node:fs";

export const RULES = JSON.parse(
  readFileSync(new URL("../../wiki/규칙.json", import.meta.url), "utf-8")
);

/** DOM 호출을 전부 무해하게 받아넘기는 껍데기. 값은 els로 들여다본다. */
export function loadTools() {
  const html = readFileSync(new URL("../도구.html", import.meta.url), "utf-8");
  const js = html.split("<script>")[1].split("</script>")[0];

  const els = new Map();
  const make = () => ({
    innerHTML: "", textContent: "", value: "", disabled: false, hidden: false,
    files: [], dataset: {},
    addEventListener() {}, setAttribute() {}, click() {},
    closest: () => ({ classList: { toggle() {} } }),
    classList: { toggle() {}, contains: () => false },
  });
  const document = {
    getElementById(id) {
      if (!els.has(id)) els.set(id, make());
      return els.get(id);
    },
    createElement: make,
    addEventListener() {},
  };
  const window = { addEventListener() {} };

  new Function("document", "window", "alert", "confirm", "TextEncoder",
    js.replace(/^"use strict";/, "") + "\nwindow.TOOLS = window.TOOLS;"
  )(document, window, () => {}, () => true, TextEncoder);

  return { ...window.TOOLS, els, document };
}

export function reporter() {
  let pass = 0, fail = 0;
  const ok = (cond, label, extra = "") => {
    if (cond) { pass++; console.log(`PASS  ${label}`); }
    else { fail++; console.log(`★FAIL★  ${label} ${extra}`); }
  };
  const done = () => {
    console.log(`\n${pass} pass, ${fail} fail`);
    if (fail) process.exit(1);
  };
  return { ok, done };
}
