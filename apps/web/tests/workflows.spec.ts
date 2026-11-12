import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

function wav() {
  const data = Buffer.alloc(16044);
  data.write("RIFF", 0);
  data.writeUInt32LE(16036, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(16000, 24);
  data.writeUInt32LE(32000, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(16000, 40);
  return data;
}

test("import, edit Arabic reference, verify, reload, and inspect history", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Recording library" }),
  ).toBeVisible();
  await page.locator("input[type=file]").setInputFiles({
    name: "Owner memo.wav",
    mimeType: "audio/wav",
    buffer: wav(),
  });
  await page.getByRole("button", { name: "Open Owner memo.wav" }).click();
  const reference = page.getByRole("textbox", {
    name: "Ground-truth transcript",
  });
  await reference.fill("مرحبا بالعالم — İzmir");
  await expect(page.getByText(/Saved · revision/)).toBeVisible();
  await page.getByRole("button", { name: "Mark verified" }).click();
  await expect(
    page.getByText("Verified reference", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Open Owner memo.wav" }).click();
  await expect(reference).toHaveValue("مرحبا بالعالم — İzmir");
  await page.getByRole("button", { name: "Version history" }).click();
  await expect(page.getByText("Revision 2")).toBeVisible();
  await page.getByRole("button", { name: "Close history" }).click();
  await page.route("**/api/v1/recordings/*/reference", (route) =>
    route.request().method() === "PUT"
      ? route.fulfill({
          status: 503,
          json: { detail: "Temporary offline test" },
        })
      : route.continue(),
  );
  await reference.fill("Unsaved private draft — مرحبا");
  await expect(page.getByRole("alert")).toContainText("Temporary offline test");
  await page.getByRole("link", { name: "Experiments", exact: true }).click();
  await page.getByRole("link", { name: "Library", exact: true }).click();
  await page.getByRole("button", { name: "Open Owner memo.wav" }).click();
  await expect(reference).toHaveValue("Unsaved private draft — مرحبا");
  await page.unroute("**/api/v1/recordings/*/reference");
  await reference.click();
  await reference.blur();
  await expect(page.getByText(/Saved · revision/)).toBeVisible();
  await page.getByRole("link", { name: "Experiments", exact: true }).click();
  await expect(page.getByText("No installed checkpoints")).toBeVisible();
  await page.getByRole("link", { name: "Review", exact: true }).click();
  await expect(
    page.getByText("A fair review starts with real outputs"),
  ).toBeVisible();
});

test("all workspaces have honest empty states and theme switch works", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Toggle appearance" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "Compare", exact: true }).click();
  await expect(page.getByText("Evidence before rankings")).toBeVisible();
  await page.getByRole("link", { name: "Devices", exact: true }).click();
  await expect(page.getByText("Inference belongs on the iPhone")).toBeVisible();
  await page.getByRole("link", { name: "Model registry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Model registry" }),
  ).toBeVisible();
  await expect(page.getByText("not-installed").first()).toBeVisible();
});

test("five-output blind keyboard review, reveal, comparison drilldown and score snapshots", async ({
  page,
}, info) => {
  execFileSync(
    resolve("../../.venv/bin/python"),
    [
      resolve("../../tests/seed_browser.py"),
      info.config.metadata.testData as string,
    ],
    { cwd: process.cwd() },
  );
  // Tall viewport so the drag never needs to scroll mid-gesture.
  await page.setViewportSize({ width: 1400, height: 3000 });
  await page.goto("/#review");
  await expect(page.locator(".output-row")).toHaveCount(5);
  await expect(page.getByText("ui-fixture-0", { exact: true })).toHaveCount(0);
  // Target text is hidden by default so it cannot bias the ranking.
  await expect(page.getByText("FROZEN VERIFIED REFERENCE")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Word diff" })).toHaveCount(0);
  await expect(page.locator("mark")).toHaveCount(0);
  await page.getByLabel("Target text").check();
  await expect(page.getByText("FROZEN VERIFIED REFERENCE")).toBeVisible();
  await page.getByRole("button", { name: "Word diff", exact: true }).click();
  await expect(page.locator("mark").first()).toBeVisible();
  for (let i = 1; i <= 5; i++) {
    await page
      .getByRole("radio", { name: `Output ${i} Faithfulness 4`, exact: true })
      .click();
    await page
      .getByRole("radio", { name: `Output ${i} Readability 4`, exact: true })
      .click();
    await page.getByRole("button", { name: "Add to ranking" }).first().click();
  }
  const ranking = page.getByLabel("Ranked outputs");
  const order = () =>
    ranking.locator(".output-heading strong").allTextContents();
  expect(await order()).toEqual([
    "Output 1",
    "Output 2",
    "Output 3",
    "Output 4",
    "Output 5",
  ]);
  // Drag the last card to the top, then tie the old first card with it.
  await page
    .getByLabel("Drag Output 5")
    .dragTo(ranking.locator("article").filter({ hasText: "Output 1" }));
  expect(await order()).toEqual([
    "Output 5",
    "Output 1",
    "Output 2",
    "Output 3",
    "Output 4",
  ]);
  await page.getByLabel("Output 1 ties with the card above").check();
  await expect(
    ranking.locator("article").filter({ hasText: "Output 1" }),
  ).toContainText("Rank 1");
  await expect(
    ranking.locator("article").filter({ hasText: "Output 2" }),
  ).toContainText("Rank 3");
  await expect(page.getByText("Progress saved")).toBeVisible();
  // Ranking survives a reload because it is saved on the server. Tied cards share a
  // rank, so their relative order is not saved and they come back sorted by label.
  await page.reload();
  await expect(page.locator(".output-row")).toHaveCount(5);
  expect(await order()).toEqual([
    "Output 1",
    "Output 5",
    "Output 2",
    "Output 3",
    "Output 4",
  ]);
  await expect(page.getByLabel("Output 5 ties with the card above")).toBeChecked();
  await page.screenshot({ path: "/tmp/stt-lab-review.png", fullPage: true });
  await page.getByRole("button", { name: "Lock & reveal identities" }).click();
  await expect(
    page.getByText("Identities revealed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(page.locator(".data-table tbody tr")).toHaveCount(5);
  await page.getByLabel("Advance ui-fixture-0 to phone").check();
  await page.getByLabel("ui-fixture-0 note").fill("best Arabic");
  const noteSaved = page.waitForResponse(
    (r) =>
      r.url().includes("/candidates/ui-fixture-0") &&
      (r.request().postData() || "").includes("best Arabic") &&
      r.ok(),
  );
  await page.getByLabel("ui-fixture-0 note").blur();
  await noteSaved;
  await page.reload();
  await page.getByRole("button", { name: "Shortlist", exact: true }).click();
  await expect(page.getByLabel("Advance ui-fixture-0 to phone")).toBeChecked();
  await expect(page.getByLabel("ui-fixture-0 note")).toHaveValue("best Arabic");
  await page.getByRole("link", { name: "Compare", exact: true }).click();
  await expect(page.locator(".compare-table tbody tr")).toHaveCount(5);
  await page.locator(".compare-table .model-cell").first().click();
  await expect(page.getByRole("dialog")).toContainText("Synthetic UI fixture");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page
    .getByRole("button", { name: "Rescore current verified references" })
    .click();
  await expect(
    page.getByLabel("Evaluation snapshot").locator("option"),
  ).toHaveCount(2);
  await page.getByRole('link',{name:'Experiments',exact:true}).click();
  await page.getByLabel('Profiling trace file').setInputFiles({name:'Synthetic trace fixture.zip',mimeType:'application/zip',buffer:Buffer.from('opaque trace fixture; not an energy measurement')});
  await expect(page.getByRole('link',{name:'Synthetic trace fixture.zip'})).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Library", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Recording library" }),
  ).toBeVisible();
  await page.screenshot({ path: "/tmp/stt-lab-mobile.png", fullPage: true });
});
