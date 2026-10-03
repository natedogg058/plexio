import { test, expect } from '@playwright/test';

const manifest = 'https://plexio.example.test/test-session/manifest.json';
const defaultConnection = 'https://plex.example.test:32400';

async function setup(page, connection = defaultConnection) {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() =>
    sessionStorage.setItem('plexToken', 'fixture-only'),
  );
  await page.route('https://plex.tv/api/v2/user', (route) =>
    route.fulfill({ json: { username: 'Browser test', thumb: '' } }),
  );
  await page.route('**/api/v1/plex-resources*', (route) =>
    route.fulfill({
      json: [
        {
          name: 'Test Plex',
          provides: 'server',
          accessToken: 'fixture-only',
          owned: true,
          connections: [
            {
              uri: connection,
              address: new URL(connection).hostname,
              port: Number(new URL(connection).port || 443),
              local: false,
              relay: false,
            },
          ],
        },
      ],
    }),
  );
  await page.route('**/api/v1/public-config', (route) =>
    route.fulfill({
      json: {
        base_url: 'https://plexio.example.test',
        legacy_urls_enabled: false,
      },
    }),
  );
  await page.route('**/api/v1/plex-sections*', (route) =>
    route.fulfill({
      json: {
        sections: [{ key: '1', title: 'Movies', type: 'movie' }],
      },
    }),
  );
  await page.route('**/api/v1/sessions*', (route) =>
    route.fulfill({ json: { session_id: 'test-session' } }),
  );
  await page.goto('/');
  await page.getByRole('combobox', { name: 'Plex Server' }).click();
  await page.getByRole('option', { name: 'Test Plex' }).click();
  return errors;
}

async function configure(page) {
  for (const name of ['Discovery URL', 'Streaming URL']) {
    await page.getByRole('combobox', { name, exact: true }).click();
    await page.getByRole('option').click();
  }
  await page.getByRole('checkbox', { name: 'Movies', exact: true }).check();
}

// Hold the response until the test has exercised the in-flight UI.
async function holdSession(page) {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let received;
  const request = new Promise((resolve) => {
    received = resolve;
  });
  await page.route('**/api/v1/sessions*', async (route) => {
    received(route.request().postDataJSON());
    await gate;
    await route.fulfill({ json: { session_id: 'test-session' } });
  });
  return { request, release };
}

async function clipboardStub(page, denied = false) {
  await page.evaluate((denied) => {
    window.copiedValues = [];
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        write: async (items) => {
          const blob = await items[0].getType('text/plain');
          if (denied) throw new DOMException('Denied', 'NotAllowedError');
          window.copiedValues.push(await blob.text());
        },
        writeText: async (text) => {
          if (denied) throw new DOMException('Denied', 'NotAllowedError');
          window.copiedValues.push(text);
        },
      },
    });
    document.execCommand = () => false;
  }, denied);
}

for (const [connection, address] of [
  ['https://192-168-1-2.server.plex.direct:32400', '192.168.1.2:32400'],
  ['http://192.168.1.2:32400', '192.168.1.2:32400'],
  ['https://plex.example.test', 'plex.example.test'],
  ['http://[2001:db8::1]:32400', '[2001:db8::1]:32400'],
]) {
  test(`connection tests display results for ${connection}`, async ({
    page,
  }) => {
    const errors = await setup(page, connection);
    await configure(page);
    await page.route('**/api/v1/test-connection*', (route) =>
      route.fulfill({ json: { success: true } }),
    );
    await page.route(`${connection}/`, (route) =>
      route.fulfill({ body: 'OK' }),
    );
    await page
      .getByRole('button', { name: 'Test', exact: true })
      .nth(0)
      .click();
    await expect(
      page.getByText(
        `Plexio backend successfully accessed your server at ${address}.`,
        { exact: true },
      ),
    ).toBeVisible();
    await page
      .getByRole('button', { name: 'Test', exact: true })
      .nth(1)
      .click();
    await expect(
      page
        .getByText(
          `Your device successfully accessed the Streaming URL at ${address}.`,
          { exact: false },
        )
        .first(),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('connection failures show feedback and allow retry', async ({ page }) => {
  const errors = await setup(page);
  await configure(page);
  await page.route('**/api/v1/test-connection*', (route) => route.abort());
  await page.route(`${defaultConnection}/`, (route) => route.abort());
  for (const [index, label] of ['Discovery', 'Streaming'].entries()) {
    await page
      .getByRole('button', { name: 'Test', exact: true })
      .nth(index)
      .click();
    await expect(
      page.getByText(`${label} URL Test Failed!`, { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Test', exact: true }).nth(index),
    ).toBeEnabled();
  }
  expect(errors).toEqual([]);
});

test('native clipboard starts in the click gesture before a delayed response', async ({
  page,
  context,
  browserName,
}) => {
  const errors = await setup(page);
  await configure(page);
  if (browserName === 'chromium') {
    // Headless Chromium has no permission prompt. WebKit keeps its native
    // user-gesture restriction; both engines still use the real clipboard.
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  }
  await page.evaluate(() => {
    const write = navigator.clipboard.write.bind(navigator.clipboard);
    navigator.clipboard.write = (items) => {
      window.clipboardGesture = navigator.userActivation.isActive;
      return write(items);
    };
  });
  const session = await holdSession(page);
  await page
    .getByRole('button', { name: 'Copy manifest URL', exact: true })
    .click();
  await session.request;
  expect(await page.evaluate(() => window.clipboardGesture)).toBe(true);
  await expect(
    page.getByRole('button', { name: 'Install', exact: true }),
  ).toBeDisabled();
  // Deliberately cross a task boundary: WebKit must reserve access in the click.
  await page.waitForTimeout(1200);
  session.release();
  await expect(
    page.getByText('Manifest URL copied.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Manifest URL', { exact: true })).toHaveValue(
    manifest,
  );
  if (browserName === 'chromium') {
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      manifest,
    );
  }
  expect(errors).toEqual([]);
});

for (const action of ['Copy manifest URL', 'Install']) {
  test(`${action} rejects settings changed during generation`, async ({
    page,
  }) => {
    const errors = await setup(page);
    await configure(page);
    await clipboardStub(page);
    const session = await holdSession(page);
    await page.getByRole('button', { name: action, exact: true }).click();
    await session.request;
    await page
      .getByRole('switch', { name: 'Include Plex.tv URL', exact: true })
      .click();
    session.release();
    await expect(
      page
        .getByRole('alert')
        .filter({ hasText: 'Settings changed. Generate a new manifest URL.' }),
    ).toBeVisible();
    await expect(page.getByLabel('Manifest URL', { exact: true })).toHaveCount(
      0,
    );
    expect(await page.evaluate(() => window.copiedValues)).toEqual([]);
    await expect(
      page.getByRole('button', { name: action, exact: true }),
    ).toBeEnabled();
    expect(page.url()).toBe('http://127.0.0.1:4173/');
    // A fresh request with the revised settings succeeds.
    await page
      .getByRole('button', { name: 'Copy manifest URL', exact: true })
      .click();
    await expect(
      page.getByText('Manifest URL copied.', { exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => window.copiedValues)).toEqual([manifest]);
    expect(errors).toEqual([]);
  });
}

test('blocked clipboard offers manual selection and HTTP fallback, then clears stale URL', async ({
  page,
}) => {
  const errors = await setup(page);
  await configure(page);
  await clipboardStub(page, true);
  await page
    .getByRole('button', { name: 'Copy manifest URL', exact: true })
    .click();
  const field = page.getByLabel('Manifest URL', { exact: true });
  await expect(field).toHaveValue(manifest);
  await page.getByRole('button', { name: 'Copy URL', exact: true }).click();
  await expect(
    page.getByText('Select the manifest URL and copy it manually.', {
      exact: true,
    }),
  ).toBeVisible();
  await field.click();
  expect(
    await field.evaluate((el) => el.selectionEnd - el.selectionStart),
  ).toBe(manifest.length);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });
    document.execCommand = (command) => {
      if (command !== 'copy') throw new Error('Unexpected command');
      window.copiedValues.push(document.activeElement.value);
      return true;
    };
  });
  await page.getByRole('button', { name: 'Copy URL', exact: true }).click();
  await expect(
    page.getByText('Manifest URL copied.', { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.copiedValues)).toEqual([manifest]);
  await page
    .getByRole('switch', { name: 'Include Plex.tv URL', exact: true })
    .click();
  await expect(field).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('validation and session failures never expose a manifest and allow retry', async ({
  page,
}) => {
  const errors = await setup(page);
  await clipboardStub(page);
  let requests = 0;
  await page.route('**/api/v1/sessions*', (route) => {
    requests++;
    return route.fulfill({
      status: 503,
      json: { detail: 'Fixture unavailable' },
    });
  });
  await page
    .getByRole('button', { name: 'Copy manifest URL', exact: true })
    .click();
  await expect(
    page
      .getByRole('alert')
      .filter({ hasText: 'Please check the highlighted fields.' }),
  ).toBeVisible();
  expect(requests).toBe(0);
  await configure(page);
  await page
    .getByRole('button', { name: 'Copy manifest URL', exact: true })
    .click();
  await expect(
    page
      .getByRole('alert')
      .filter({ hasText: 'could not create a secure install session' }),
  ).toBeVisible();
  await expect(page.getByLabel('Manifest URL', { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Copy manifest URL', exact: true }),
  ).toBeEnabled();
  expect(await page.evaluate(() => window.copiedValues)).toEqual([]);
  expect(requests).toBe(1);
  expect(errors).toEqual([]);
});
