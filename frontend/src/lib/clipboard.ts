// Call from the original user gesture, before awaiting validation or a request.
// Safari requires write() to start during that gesture; the text can arrive later.
export async function copyText(
  text: string | Promise<string>,
): Promise<boolean> {
  try {
    if (typeof text === 'string') {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } else if (
      navigator.clipboard?.write &&
      typeof ClipboardItem !== 'undefined'
    ) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/plain': text.then(
            (value) => new Blob([value], { type: 'text/plain' }),
          ),
        }),
      ]);
      return true;
    }
  } catch {
    // Keep the URL available for a fresh click or manual copying if blocked.
  }

  // Support copying from self-hosted HTTP pages without the Clipboard API.
  // This path also needs a direct click and an already generated URL.
  if (typeof text !== 'string') return false;
  const previousFocus = document.activeElement;
  const input = document.createElement('textarea');
  input.value = text;
  input.readOnly = true;
  input.style.position = 'fixed';
  input.style.opacity = '0';
  document.body.appendChild(input);
  input.select();
  input.setSelectionRange(0, text.length);
  try {
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    input.remove();
    if (previousFocus instanceof HTMLElement) previousFocus.focus();
  }
}
