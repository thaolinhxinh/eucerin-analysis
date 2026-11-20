// n8n Code node: 02 | Config - Vercel, Drive, Telegram
// Điền 3 ID bên dưới. Không đặt API key trong file này; dùng Header Auth credential.
const cfg = {
  apiBaseUrl: 'https://eucerin-ml-automation.vercel.app',
  sourceFileId: 'PASTE_DRIVE_CSV_FILE_ID',
  outputFolderId: 'PASTE_OUTPUT_FOLDER_ID',
  telegramChatId: 'PASTE_TELEGRAM_CHAT_ID',
};

for (const [key, value] of Object.entries(cfg)) {
  if (!value || value.startsWith('PASTE_')) {
    throw new Error(`Configure ${key} in this Code node first`);
  }
}

if (!/^https:\/\/[^/]+$/.test(cfg.apiBaseUrl)) {
  throw new Error('apiBaseUrl must be HTTPS without a trailing slash');
}

return [{ json: cfg }];
