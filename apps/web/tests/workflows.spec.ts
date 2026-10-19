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
  await page.goto("/#review");
  await expect(page.locator(".output-row")).toHaveCount(5);
  await expect(page.getByText("ui-fixture-0", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Word diff", exact: true }).click();
  await expect(page.locator("mark").first()).toBeVisible();
  for (let i = 1; i <= 5; i++) {
    await page
      .getByLabel(`Output ${i} Faithfulness`, { exact: true })
      .selectOption("4");
    await page
      .getByLabel(`Output ${i} Readability`, { exact: true })
      .selectOption("4");
    await page
      .getByLabel(`Output ${i} Rank`, { exact: true })
      .selectOption(String(i));
  }
  await page.screenshot({ path: "/tmp/stt-lab-review.png", fullPage: true });
  await page.getByRole("button", { name: "Lock & reveal identities" }).click();
  await expect(
    page.getByText("Identities revealed", { exact: true }),
  ).toBeVisible();
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
