/**
 * Process entry point. Boots the Express app and starts listening.
 */

import { createApp } from './app';

const PORT = Number(process.env.PORT ?? 3000);

const app = createApp();
app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`sample-api listening on http://localhost:${PORT}`);
  console.log(`Try: curl http://localhost:${PORT}/health`);
});
