import { expect, type Page, test } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "";
const TEMP = process.env.E2E_TEMP_PASSWORD ?? "";
const PASSWORD = process.env.E2E_NEW_PASSWORD ?? "e2e-test-passphrase-2026";

test.describe.configure({ mode: "serial" });

async function signIn(page: Page, password: string) {
  await page.goto("/login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", password);
  await page.click("button[type=submit]");
}

test("pages need sign-in, and security headers are set", async ({ page, request }) => {
  await page.goto("/explorer");
  await expect(page).toHaveURL(/\/login\?next=%2Fexplorer/);
  await expect(page.getByRole("img", { name: "Connectly" })).toBeVisible();
  const res = await request.get("/login");
  expect(res.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(res.headers()["x-content-type-options"]).toBe("nosniff");
  const api = await request.get("/api/backend/api/v1/stats");
  expect(api.status()).toBe(401);
});

test("first sign-in forces a password change", async ({ page }) => {
  test.skip(!EMAIL || !TEMP, "E2E_EMAIL and E2E_TEMP_PASSWORD are required");
  await signIn(page, "definitely-wrong-password");
  await expect(page.getByText("The e-mail or password is incorrect.")).toBeVisible();
  await signIn(page, TEMP);
  await expect(page).toHaveURL(/\/account\/password/);
  await page.fill("#current_password", TEMP);
  await page.fill("#new_password", PASSWORD);
  await page.fill("#confirm", PASSWORD);
  await page.click("button[type=submit]");
  await expect(page).toHaveURL(/\/$/);
  const cookie = (await page.context().cookies()).find((c) => c.name === "ci_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie.includes("ci_session"))).toBe(false);
});

test.describe("signed in", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!EMAIL, "E2E_EMAIL is required");
    await signIn(page, PASSWORD);
    await expect(page).toHaveURL(/\/$/);
  });

  test("dashboard shows real counts @mobile", async ({ page }) => {
    await expect(page.getByText("First implementation state")).toBeVisible();
    await expect(page.getByText("774", { exact: true })).toBeVisible();
    await expect(page.getByText("9,308", { exact: true })).toBeVisible();
  });

  test("explorer colours Adamawa LGAs and opens a ward profile", async ({ page }) => {
    const ids = await page.evaluate(async () => {
      const st = await fetch("/api/backend/api/v1/areas?level=state").then((r) => r.json());
      const ad = st.find((x: { name: string }) => x.name === "Adamawa").id;
      const lgas = await fetch(`/api/backend/api/v1/areas/${ad}/children`).then((r) => r.json());
      const demsa = lgas.find((x: { name: string }) => x.name === "Demsa").id;
      const wards = await fetch(`/api/backend/api/v1/areas/${demsa}/children`).then((r) => r.json());
      return { ad, bille: wards.find((x: { name: string }) => x.name === "Bille").id };
    });
    await page.goto(`/explorer?area=${ids.ad}`);
    await expect(page.getByText("Colour local government areas by")).toBeVisible();
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    await page.goto(`/areas/${ids.bille}`);
    await expect(page.getByRole("heading", { name: "Bille" })).toBeVisible();
    await expect(page.getByText("12,867")).toBeVisible();
    await expect(page.getByText("Technology access gaps")).toBeVisible();
  });

  test("directory: create, publish, match, report, retire", async ({ page }) => {
    await page.goto("/directory/organisations/new");
    await page.fill("#org-name", "E2E test organisation");
    await page.selectOption("#org-org_type", "startup");
    await page.fill("#org-source_description", "Automated end-to-end test record");
    await page.click("button[type=submit]");
    await expect(page).toHaveURL(/organisations\/\d+$/);
    await page.getByRole("link", { name: "Add solution" }).click();
    await expect(page).toHaveURL(/solutions\/new$/);
    // Earlier pages can stay mounted but hidden, so scope to the visible solution form.
    const form = page.locator("form:has(#summary)");
    await form.locator("#name").fill("E2E test solution");
    await page.selectOption("#sector", "health");
    await page.check('input[value="health.telemedicine"]');
    await page.fill("#summary", "Automated end-to-end test record; retired by the test.");
    await page.selectOption("#internet_requirement", "sms_ussd");
    await page.fill("#source_description", "Automated end-to-end test record");
    await page.click('button:has-text("Save as draft")');
    await expect(page).toHaveURL(/solutions\/\d+$/);
    const solutionUrl = page.url();
    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Published", { exact: true })).toBeVisible();

    await page.goto("/matching");
    await page.locator("form:has(#m-sector) select[data-level=state]").selectOption({ label: "Adamawa" });
    await page.locator("#m-need").selectOption("health.telemedicine");
    await page.getByRole("button", { name: "Find matching solutions" }).click();
    await expect(page.getByText("E2E test solution").first()).toBeVisible();
    await page.getByRole("button", { name: "Save as report" }).click();
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByText("Download PDF").click()]);
    expect(download.suggestedFilename()).toMatch(/^connectly-\d+-.*\.pdf$/);

    await page.goto(solutionUrl);
    await page.getByRole("button", { name: "Retire" }).click();
    await page.getByRole("button", { name: "Retire" }).last().click();
    await expect(page.getByText("Retired", { exact: true })).toBeVisible();
  });

  test("needs, intelligence and market entry report gaps honestly", async ({ page }) => {
    await page.goto("/needs?sector=agriculture&level=lga");
    await expect(page.getByText(/No open indicator for agriculture/)).toBeVisible();
    await page.goto("/intelligence");
    // Earlier pages can stay mounted but hidden; scope to this page's form.
    await page.locator("form:has(#i-sector) select[data-level=state]").selectOption({ label: "Adamawa" });
    await page.getByRole("button", { name: "Build brief" }).click();
    await expect(page.getByText(/Evidence \(\d+\)/)).toBeVisible();
    await page.goto("/market-entry");
    await page.locator('form:has(#me-sector) label:has-text("Adamawa") input').check();
    await page.getByRole("button", { name: "Analyse" }).click();
    await expect(page.getByText("Recommended entry strategy")).toBeVisible();
    await expect(page.getByText(/Market demand .* is not measured/)).toBeVisible();
  });

  test("admin pages and sign-out", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByText("Recent dataset loads")).toBeVisible();
    await page.goto("/admin/audit");
    await expect(page.getByText("login", { exact: true }).first()).toBeVisible();
    await page.locator("button[aria-haspopup=menu]").click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });
});
