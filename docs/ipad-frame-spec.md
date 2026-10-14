# iPad Pro 預覽外框規格 / iPad Pro Preview Frame Spec

來源 Source: `zhongerxin/iPhone-use` @ `main` 5cc2fa8（`makcheunghei/ipad-use` 尚未存在／未公開，clone 失敗）。
行號以該 commit 為準 Line refs are against that commit. 參考實作草稿 Reference draft diff (passes 56/56 widget tests): `/workspace/ipad-use-spec/reference-draft.diff`（亦存於 `git stash list` → "ipad-frame draft (reference)"）。

## 0. 架構重點 Architecture facts（必讀）
- 預覽 UI 原始碼：`ui/index.html`、`ui/style.css`、`ui/src/app.ts`；`npm run build --prefix ui` 會生成 **`assets/phone-screen.html`**（自包含，CI 會 `git diff --exit-code` 檢查，所以改完必須 rebuild 並 commit 該檔）。
- 外框實際尺寸由 JS `fitFrame()`（`ui/src/app.ts:242-268`）根據**實時畫面像素**計算並以 inline style 設 `width/height/--bezel/--screen-radius`，同時自動設 `data-orientation`（landscape/portrait）。CSS `aspect-ratio` 只係未有畫面前嘅預設。→ 方向切換**已自動**，毋須另加按鈕。
- `scripts/check_screen_ui.py` 斷言 **只可有 3 個 `<button>`、無 `<input>/<form>/<a>`** → **唔好加 orientation/model toggle 按鈕**。改用 data 屬性：`data-orientation`（現有，自動）+ 新增 `data-model="11|13"`（由 model 名自動推斷）。
- 冇側邊 panel：佈局係直向 flex column（`#status` 上、`#stage` 中、`#toolbar` 下，`style.css` `#app`/`#stage`）。`#stage` 已是 flex:1，`fitFrame` 以 stage 尺寸 × 0.96 fit，所以 landscape 自然適配；**唔使 reflow**。（可選：寬屏 ≥720px 且 aspect ≥16/10 時把 toolbar 移去右邊直排——不建議，非必要。）

## 1. 尺寸 Tokens
| Token | 值 Value | 說明 |
|---|---|---|
| `--ipad-aspect` (11", portrait) | `1668/2420` | iPad Pro 11" (M4) |
| `--ipad-aspect` (13", portrait) | `2064/2752` | iPad Pro 13" (M4) |
| landscape | `2420/1668`, `2752/2064` | 對調 swap |
| `--ipad-w` / `--ipad-h` | 1668/2420 或 2064/2752（landscape 對調） | 無單位數字 unitless |
| `--bezel` | 短邊 × **0.022**（JS: `shortSide * .022`，取代 `.024` @ app.ts:248） | 均勻薄邊 uniform |
| `--frame-radius` | 短邊 × **0.075** | 大圓角 |
| `--screen-radius` | `--frame-radius − --bezel`（JS: `(shortSide*.075 - inset)*scale`，取代 app.ts:256 `.12`） | 同心 concentric |
| `--frame-body` | `#1C1C1E` | Space Black 機身 |
| `--frame-edge` | `rgba(255,255,255,.08)` | 邊緣高光 |
| `--frame-screen` | `#000` | 屏幕底色（取代 `#050609` @ style.css:28） |
| `--camera-size` | `max(3px, var(--bezel)*.32)` | 前鏡頭點 |
| 預設 size | `{ width: 1668, height: 2420 }`（取代 app.ts:243 `440×956`） | 未有畫面時 |

## 2. 前鏡頭 Camera dot
iPad Pro (M4) 前鏡頭在**橫向長邊**：
- Landscape 橫向：上邊框正中 top-centre — `left:50%; top:calc(var(--bezel)/2)`
- Portrait 直向：左邊框正中 left-centre — `left:calc(var(--bezel)/2); top:50%`
- 無 Dynamic Island、無 Home 鍵、無 side buttons；可選頂部按鈕（subtle top button，`#2c2c2e`）：portrait 在頂邊右側，landscape 在頂邊左端。

## 3. 要刪除 Delete
`ui/style.css`
- L26 `#device{…aspect-ratio:460/976…金屬漸變 background…}` → 以 §5 取代
- L27 `#device::before{…}` → 以 §5 取代（改為細高光）
- L30–35 `.side-button` `.action-button` `.volume-up` `.volume-down` `.power-button` `.receiver`
- L37 plain 隱藏規則 → 改為隱藏 `.top-button,.camera`（§5）
- L38–43 `#device[data-orientation="landscape"] .side-button/.action-button/.volume-*/.power-button/.receiver`
- L80–83 `.dynamic-island`、`#device[data-appearance="dynamic-island"] .dynamic-island`、`.dynamic-island::after`、landscape `.dynamic-island`

`ui/index.html`
- L17–21 四個 `.side-button` div + `.receiver` → 換成 `<div class="top-button" aria-hidden="true"></div>` + `<div class="camera" aria-hidden="true"></div>`
- L42 `<div class="dynamic-island" …>`
- L16 `#device` 加 `data-model="11"`

`ui/src/app.ts`
- L32 `type DeviceAppearance = 'plain' | 'rounded' | 'dynamic-island'` → `'plain' | 'ipad-pro'`
- L98–122 `ISLAND_MODELS` / `ROUNDED_MODELS` / `appearanceForModel` → 改為：
```ts
function appearanceForModel(value: string): DeviceAppearance {
  const name = value.trim().replace(/\s+/g, ' ').toLowerCase();
  return /^ipad pro\b/.test(name) ? 'ipad-pro' : 'plain'; // Home-button iPads / unknown → plain
}
function sizeClassForModel(value: string): '11' | '13' {
  return /\b13(?:[- ]?inch|"|\b)/i.test(value) ? '13' : '11';
}
```
- L339 stream 重置：`model.textContent = 'iPad'; device.dataset.model = '11';`
- L347–350：設 appearance 後加 `device.dataset.model = sizeClassForModel(preview.device.model);`

## 4. 佈局 Layout rules
- Portrait/landscape 均由 `fitFrame()` 按實時畫面決定，外框 = 畫面 + 2×bezel，scale = 0.96×min(stageW/outerW, stageH/outerH) → 永遠 fit viewport。
- CSS fallback（JS 前）：`width:min(100%,560px); max-height:100%; aspect-ratio:var(--ipad-aspect)`。
- `#status`、`#toolbar` 維持上／下，不變；toast 位置不變。
- Plain（非 iPad Pro）維持無外框矩形屏（現有行為）。

## 5. Ready-to-paste CSS（取代 L26–27、L30–43、L80–83）
```css
/* iPad Pro frame tokens. fitFrame() sets live --bezel/--screen-radius and size. */
#device{--ipad-aspect:1668/2420;--ipad-w:1668;--ipad-h:2420;--bezel:0px;--screen-radius:0px;--frame-radius:calc(var(--screen-radius) + var(--bezel));--frame-body:#1C1C1E;--frame-edge:rgba(255,255,255,.08);--frame-screen:#000;--camera-size:max(3px,calc(var(--bezel) * .32));position:relative;width:min(100%,560px);max-height:100%;aspect-ratio:var(--ipad-aspect);flex:none;isolation:isolate;border-radius:var(--frame-radius);background:var(--frame-body);box-shadow:inset 0 0 0 1px var(--frame-edge),0 0 0 .7px #000000b3,0 12px 28px -14px #00000055,0 4px 8px -4px #00000033;user-select:none;pointer-events:none}
#device[data-model="13"]{--ipad-aspect:2064/2752;--ipad-w:2064;--ipad-h:2752}
#device[data-orientation="landscape"]{--ipad-aspect:2420/1668;--ipad-w:2420;--ipad-h:1668}
#device[data-orientation="landscape"][data-model="13"]{--ipad-aspect:2752/2064;--ipad-w:2752;--ipad-h:2064}
#device::before{content:"";position:absolute;inset:.5px;z-index:1;border-radius:calc(var(--frame-radius) - .5px);box-shadow:inset 0 0 0 .5px var(--frame-edge);pointer-events:none}
/* #screen: change background:#050609 → background:var(--frame-screen) */
.top-button{position:absolute;z-index:0;top:calc(var(--bezel) * -.12);right:12%;width:9%;height:calc(var(--bezel) * .14);border-radius:999px;background:#2c2c2e;pointer-events:none}
#device[data-orientation="landscape"] .top-button{right:auto;left:6%;width:6.5%}
.camera{position:absolute;z-index:3;left:calc(var(--bezel) / 2);top:50%;width:var(--camera-size);height:var(--camera-size);transform:translate(-50%,-50%);border-radius:50%;background:radial-gradient(circle at 40% 35%,#2a3a55 0%,#0d1320 55%,#000 80%);box-shadow:0 0 0 .5px #ffffff10;pointer-events:none}
#device[data-orientation="landscape"] .camera{left:50%;top:calc(var(--bezel) / 2)}
#device[data-appearance="plain"]{border-radius:0;background:none;box-shadow:none}
#device[data-appearance="plain"]::before,#device[data-appearance="plain"] .top-button,#device[data-appearance="plain"] .camera{display:none}
```

## 6. 文案對照表 Copy table（UI 為簡體中文 zh-CN，保持簡體；中英之間加空格）
| File:Line | 原文 | 改為 |
|---|---|---|
| ui/index.html:6 | `iPhone 屏幕` | `iPad 屏幕` |
| ui/index.html:10 | aria-label `iPhone 实时屏幕` | `iPad 实时屏幕` |
| ui/index.html:12 | `<span id="model">iPhone</span>` | `iPad` |
| ui/index.html:23 | alt `iPhone 实时屏幕` | `iPad 实时屏幕` |
| ui/index.html:48 | aria-label `手机工具` | `iPad 工具` |
| ui/src/app.ts:54 | `'iPhone Use Screen'`（MCP appInfo name） | `'iPad Use Screen'` |
| ui/src/app.ts:85-86 | `请在手机上接管操作` ×3 | `请在 iPad 上接管操作` |
| ui/src/app.ts:90 | `手机正在执行操作，请稍后再试` | `iPad 正在执行操作，请稍后再试` |
| ui/src/app.ts:93 | `未连接到手机` | `未连接到 iPad` |
| ui/src/app.ts:94 | `请先解锁手机` | `请先解锁 iPad` |
| ui/src/app.ts:339 | `'iPhone'` | `'iPad'` |
| ui/src/app.ts:374 | `解锁 iPhone 后继续任务…` | `解锁 iPad 后继续任务…` |
| ui/src/app.ts:375 | `完成手机认证后…` | `完成 iPad 认证后…` |
| ui/src/app.ts:498 | `未连接到手机，请确认连接后重试` | `未连接到 iPad，请确认连接后重试` |
| ui/src/app.ts:592,594 | `请查看手机后再操作` / `请查看手机状态` | `请查看 iPad 后再操作` / `请查看 iPad 状态` |
| ui/src/app.ts:645 | `点击操作手机；…` | `点击操作 iPad；…` |
| ui/tests/widget.test.mjs | 對應斷言字串（L284,464-467,491,576,754,786）+ L607-691 機型測試 | 同步更新（見 reference diff） |

**唔好改 Do NOT rename**（外部依賴 external contracts）：
- MCP tool 名 `pua_screen_frame`、`pua_screen_action`；error code `phone_locked`、`pua_unreachable`（server 回傳）
- `assets/phone-screen.html` 檔名（server/plugin 引用）
- `server/iphone_use.py`、`skills/iphone-use*`、`IPHONE_USE_ANALYTICS` env、`.codex-plugin`/`plugin.json`/`mcp.json` 名、`ui/package.json` name `iphone-use-screen-widget`（packaging/test 依賴）
- README / CHANGELOG 屬另一範疇，未納入。

## 7. 驗收清單 Acceptance checklist
- [ ] `grep -n "460/976\|side-button\|dynamic-island\|receiver" ui/ assets/phone-screen.html` 無結果
- [ ] `grep -n "iPhone\|手机" ui/index.html ui/src/app.ts` 只剩註釋/無（測試除非刻意測 iPhone→plain）
- [ ] iPad Pro 11"/13" 型號 → `data-appearance="ipad-pro"`，`data-model` 11/13 正確；iPad Air/mini/Home-button iPad/未知 → `plain`、`--bezel:0px`
- [ ] `--screen-radius > --bezel > 0`，且 frame radius = screen radius + bezel（同心）
- [ ] Portrait：camera 喺左邊框正中；Landscape：camera 喺上邊框正中；無 side buttons
- [ ] 兩個方向外框都完整 fit 喺 stage 內；手勢座標（cursor %）不變
- [ ] 仍然只有 3 個 toolbar button
- [ ] `npm ci --prefix ui && npm run build --prefix ui && npm test --prefix ui` 全過（草稿為 56/56）
- [ ] `sh scripts/check.sh` 全過；`assets/phone-screen.html` 已 rebuild 並 commit
